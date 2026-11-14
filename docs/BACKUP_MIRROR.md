# Backup mirror: a second copy of every backup

GearCargo writes its backups to `volumes/backups` on the server's own disk. A disk
failure there loses the data and every backup of it. The backup mirror keeps a
second copy of each finished backup in a folder that you mount into the
container: a NAS share, a second disk, a USB drive.

The application only copies files into that folder. It opens no connection,
stores no address and no credentials, and no account can change where the copies
go. The folder is set once, at deployment, with `BACKUP_MIRROR_FOLDER`.

## What is copied

Every finished backup under `volumes/backups`, in the same layout:

| Folder | Contents |
|---|---|
| `<account id>/` | Personal backups: scheduled, "Backup now" and uploaded ones (`.zip`, `.zip.gcb`) |
| `system/daily/`, `system/weekly/` | The scheduled full system archives (`.tar.gz`, `.tar.gz.gcb`) |
| `system/manual/` | Archives made with `run-backup.sh manual` |
| `system/` | Full system exports made from the administrator screen |

A system archive holds the whole database and every attachment and upload. It is
the one that rebuilds an installation; a personal backup restores one person's
vehicle records. Restore state, temporary files and anything that is not a
finished backup are not copied.

A copy has the protection of its original. An unencrypted backup is readable in
the mirror by anyone who can read that folder. Turn on
[backup encryption](BACKUP_ENCRYPTION.md) before the first copy leaves the server.

## Setting it up

1. **Prepare the storage.** Use a folder that holds nothing else. Create an empty
   file named `.gearcargo-backup-mirror` in it. GearCargo writes only where it
   finds this file, so a share that failed to mount can never make the "second
   copy" land on the server's own disk.
2. **Mount it on the host**, then into the container at a path **outside**
   `/app/volumes`. The container changes the ownership of everything under
   `/app/volumes` at start, which would crawl the share and can hang the start
   while the storage is away.

   ```yaml
   services:
     gearcargo:
       environment:
         - BACKUP_MIRROR_FOLDER=/mnt/backup-mirror
       volumes:
         - type: bind
           source: /mnt/gearcargo-backups
           target: /mnt/backup-mirror
           bind:
             propagation: rslave
   ```

   `rslave` lets a share that is mounted after the container started appear
   inside it without a restart.
3. **Let the application write to it.** It writes as user and group ID 1000. On an
   NFS export, map that user to an account that may write to the folder. On an SMB
   mount, use `uid=1000,gid=1000`.
4. **Restart the container** and open Settings → Backup. The line "Second copy"
   shows the state.

Two host examples, with placeholder names. Both keep a NAS outage from blocking
the server: the mount is optional at boot, and a stalled share returns an error
instead of hanging.

```fstab
# NFS
nas.example.lan:/volume1/gearcargo-backups  /mnt/gearcargo-backups  nfs4  rw,soft,timeo=100,retrans=3,nofail,_netdev,x-systemd.automount  0 0
# SMB, with the account in a root-only credentials file
//nas.example.lan/gearcargo-backups  /mnt/gearcargo-backups  cifs  credentials=/root/.gearcargo-backups,uid=1000,gid=1000,file_mode=0600,dir_mode=0700,seal,nofail,_netdev,x-systemd.automount  0 0
```

## How it behaves

- **Every 15 minutes** the scheduler copies what the mirror lacks. A new backup
  is in the mirror within that time.
- **Each copy is checked.** It is written under a temporary name, compared with
  the original by SHA-256 and only then given its final name. A copy that does
  not match is removed and the run is reported as failed.
- **Retention follows the server.** A copy is removed once its original has been
  rotated out locally: it must be gone from the server *and* older than every
  backup the server still keeps in the same folder. A folder whose local side is
  empty is never pruned, so a wiped or damaged `volumes/backups` cannot empty the
  mirror.
- **An unreachable mirror is not an error for the application.** Backups continue
  locally, the state changes, and the next run catches up.
- **A day of failures is announced.** After 24 hours without a working mirror,
  every administrator who has notifications on gets one push notification, in
  the language of their account. The next one comes only after the mirror has
  recovered and failed again.
- **Deletions are carried over when they are deliberate.** Deleting a stored
  backup in Settings → Backup also deletes its copy. Deleting an account removes
  every backup of it from the server and then its folder from the mirror; if the
  mirror is away, the removal is retried until it succeeds. Copies of system
  archives age out with retention.

## The state on the Backup screen

| State | Meaning | What to do |
|---|---|---|
| Up to date | Every finished backup has a verified copy | Nothing |
| Waiting | No backup has been copied yet | Nothing; run a backup to see it work |
| Not reachable | The folder or its marker file is missing | Check that the share is mounted and holds `.gearcargo-backup-mirror` |
| Failed | A copy could not be written or verified | Check free space and write permission, then the server log |

The server log has one line per change of state (`Backup mirror is now …`) and
one per run that copied files. `flask scheduler-status` lists the `backup_mirror`
job with the others.

## Restoring from the mirror

- **A personal backup:** copy the file into `volumes/backups/<account id>/` on the
  server. It appears under stored backups in Settings → Backup, where it restores
  like any other. Uploading it there works too, within the upload limit.
- **A system archive:** restore it from the file, without an upload:

  ```sh
  docker compose exec -u gearcargo gearcargo flask restore-system-archive /mnt/backup-mirror/system/daily/<archive>
  ```

  See [Restore recovery](RESTORE_RECOVERY.md). A full restore also needs the
  original `ENCRYPTION_KEY` and the other secrets of the installation, and the
  backup passphrase for encrypted archives. Keep those somewhere other than the
  mirror.

Test a restore on a spare installation before you rely on the mirror.

## Limits

- The application can write to and delete from the mirror, so a compromised
  server could damage the copies. Use storage-side snapshots on the share, and an
  account or export that reaches nothing else.
- A share in the same building is a second device, not an off-site copy. Let the
  storage replicate the folder elsewhere if you need one.
- A share that refuses to set file times (some SMB mounts) still gets its copies;
  old copies are then pruned later than on the server.
- A full or read-only share reports "Failed" until space or permission returns.
- The notice is a push notification. An administrator with no device subscribed
  to notifications sees a failing mirror only on the Backup screen.
