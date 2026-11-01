"""Resource ceilings for trusted-admin system archives, including nested gzip.

All byte streams use fixed-size reads. Limits remain enabled when operators
increase them for a larger fleet; zero/negative values fail closed.
"""
import gzip
import hashlib
import resource
import os
import select
import shutil
import subprocess
import tarfile
import time
import zlib
from contextlib import contextmanager
from pathlib import Path

from flask import current_app

CHUNK = 64 * 1024
DEFAULTS = {
    'MAX_MEMBERS': 100_000,
    'MAX_MEMBER_BYTES': 2 * 1024**3,
    'MAX_ARCHIVE_BYTES': 8 * 1024**3,
    'MAX_SQL_BYTES': 8 * 1024**3,
    'MAX_MANIFEST_BYTES': 8 * 1024**2,
    'MAX_PROCESS_BYTES': 512 * 1024**2,
    'MIN_FREE_BYTES': 512 * 1024**2,
    'TIMEOUT_SECONDS': 1800,
}


class RestoreBudgetError(ValueError):
    pass


class Budget:
    def __init__(self):
        self.limits = {}
        for key, default in DEFAULTS.items():
            name = 'SYSTEM_RESTORE_' + key
            try:
                value = int(current_app.config.get(name, default))
                if value <= 0:
                    raise ValueError()
            except (TypeError, ValueError, OverflowError):
                raise RestoreBudgetError(f'{name} must be a positive integer.') from None
            self.limits[key] = value
        self.deadline = time.monotonic() + self.limits['TIMEOUT_SECONDS']

    def reject(self, key):
        raise RestoreBudgetError(
            f'System restore exceeds SYSTEM_RESTORE_{key}. '
            'Stage this backup on an adequately sized installation and configure a finite '
            'larger limit after checking capacity; see docs/RESTORE_RECOVERY.md.')

    def remaining(self):
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            self.reject('TIMEOUT_SECONDS')
        return remaining

    def check(self, key, value):
        self.remaining()
        if value > self.limits[key]:
            self.reject(key)

    def space(self, path, additional=0):
        self.remaining()
        path = Path(path)
        while not path.exists():
            path = path.parent
        if shutil.disk_usage(path).free < self.limits['MIN_FREE_BYTES'] + additional:
            raise RestoreBudgetError(
                'System restore needs more free staging/media space to preserve '
                'SYSTEM_RESTORE_MIN_FREE_BYTES. Free space or move staging to a larger '
                'persistent volume; see docs/RESTORE_RECOVERY.md.')

    def limit_process(self, process):
        # Linux deployment: cap psql's own statement buffer and pg_dump's memory,
        # not only Python's stream. Do this before sending any SQL to the child.
        try:
            maximum = self.limits['MAX_PROCESS_BYTES']
            resource.prlimit(process.pid, resource.RLIMIT_AS, (maximum, maximum))
        except ProcessLookupError:
            if process.poll() is None:
                raise

    def digest(self, path):
        checksum = hashlib.sha256()
        with open(path, 'rb') as stream:
            while chunk := stream.read(CHUNK):
                self.remaining()
                checksum.update(chunk)
        return checksum.hexdigest()

    def copy(self, source, target):
        """copytree-compatible copy with disk reserve checks during each file."""
        with open(source, 'rb') as incoming, open(target, 'wb') as outgoing:
            while chunk := incoming.read(CHUNK):
                self.space(Path(target).parent, len(chunk))
                outgoing.write(chunk)
        return target

    def sql_chunks(self, path):
        total = 0
        try:
            with gzip.open(path, 'rb') as stream:
                while chunk := stream.read(CHUNK):
                    total += len(chunk)
                    self.check('MAX_SQL_BYTES', total)
                    yield chunk
            self.remaining()
        except (gzip.BadGzipFile, EOFError, zlib.error) as exc:
            raise RestoreBudgetError('System backup SQL gzip is damaged or incomplete.') from exc

    def validate_sql(self, path):
        for _ in self.sql_chunks(path):
            pass

    def send(self, process, chunks):
        """Nonblocking pipe writes: a stalled psql cannot defeat the deadline."""
        descriptor = process.stdin.fileno()
        os.set_blocking(descriptor, False)
        for chunk in chunks:
            pending = memoryview(chunk)
            while pending:
                if not select.select([], [descriptor], [], self.remaining())[1]:
                    self.reject('TIMEOUT_SECONDS')
                try:
                    pending = pending[os.write(descriptor, pending):]
                except BlockingIOError:
                    continue
        process.stdin.close()
        try:
            process.wait(timeout=self.remaining())
        except subprocess.TimeoutExpired:
            self.reject('TIMEOUT_SECONDS')

    def output(self, process):
        """Read pg_dump output without buffering it or waiting forever."""
        descriptor = process.stdout.fileno()
        os.set_blocking(descriptor, False)
        total = 0
        while True:
            if not select.select([descriptor], [], [], self.remaining())[0]:
                self.reject('TIMEOUT_SECONDS')
            try:
                chunk = os.read(descriptor, CHUNK)
            except BlockingIOError:
                continue
            if not chunk:
                break
            total += len(chunk)
            self.check('MAX_SQL_BYTES', total)
            yield chunk
        try:
            process.wait(timeout=self.remaining())
        except subprocess.TimeoutExpired:
            self.reject('TIMEOUT_SECONDS')

    @contextmanager
    def archive(self, path):
        budget = self
        count, declared, metadata = 0, 0, False

        class SafeInfo(tarfile.TarInfo):
            # Inspect extension headers BEFORE tarfile allocates their payloads.
            # PAX/GNU extensions are legal, but recursive extension chains and
            # sparse files are not part of GearCargo's system format.
            def _proc_member(self, archive):
                nonlocal count, declared, metadata
                count += 1
                budget.check('MAX_MEMBERS', count)
                extension = self.type in (tarfile.XHDTYPE, tarfile.GNUTYPE_LONGNAME)
                if self.type in (tarfile.XGLTYPE, tarfile.GNUTYPE_LONGLINK):
                    raise RestoreBudgetError('System backup contains unsupported global/link metadata.')
                if self.size < 0 or (not extension and not (self.isfile() or self.isdir())) \
                        or self.type == tarfile.GNUTYPE_SPARSE or (self.isdir() and self.size):
                    raise RestoreBudgetError('System backup contains unsupported links/types/sizes.')
                budget.check('MAX_MEMBER_BYTES', self.size)
                if extension:
                    budget.check('MAX_MANIFEST_BYTES', self.size)
                    if metadata:
                        raise RestoreBudgetError('System backup contains chained tar extension headers.')
                    metadata = True
                else:
                    declared += self.size
                    budget.check('MAX_ARCHIVE_BYTES', declared)
                try:
                    result = super()._proc_member(archive)
                    if result is not None:
                        budget.check('MAX_MEMBER_BYTES', result.size)
                        if result.size < 0 or result.sparse is not None:
                            raise RestoreBudgetError('System backup contains unsupported sparse data/sizes.')
                    return result
                finally:
                    if extension:
                        metadata = False

        class ExpandedReader:
            total = 0

            def read(self, size):
                budget.remaining()
                chunk = expanded.read(min(size, CHUNK))
                self.total += len(chunk)
                budget.check('MAX_ARCHIVE_BYTES', self.total)
                return chunk

        try:
            with gzip.open(path, 'rb') as expanded:
                reader = ExpandedReader()
                with tarfile.open(fileobj=reader, mode='r|', bufsize=CHUNK, tarinfo=SafeInfo) as archive:
                    yield archive
                # Check the gzip trailer and bound concatenated streams/trailing
                # padding too, even after tar's end-of-archive marker.
                while reader.read(CHUNK):
                    pass
        except (gzip.BadGzipFile, EOFError, zlib.error) as exc:
            raise RestoreBudgetError('System backup gzip is damaged or incomplete.') from exc
