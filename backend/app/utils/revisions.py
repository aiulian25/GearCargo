import secrets


def next_revision(previous):
    # A fresh incarnation must not reuse an old form's revision after a personal
    # restore/import recreates the same numeric ID. Stay within JS safe integers.
    return previous + 1 if previous is not None else secrets.randbits(52) + 1
