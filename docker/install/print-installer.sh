#!/bin/sh
# Runs INSIDE the image (via the `install` entrypoint). Emits a self-extracting
# shell script to stdout that, when run on the HOST, writes docker-compose.yml,
# .env.example and setup.sh into the current directory. The assets are the exact
# files baked into this image, so they always match the image version.
set -eu

emit() { # $1 = file in /install   $2 = dest name   $3 = heredoc delimiter
    printf "cat > %s <<'%s'\n" "$2" "$3"
    cat "/install/$1"
    printf '%s\n' "$3"
    printf '\n'
}

cat <<'HDR'
#!/bin/sh
# GearCargo installer — extracted from the container image.
set -e
HDR

emit docker-compose.yml docker-compose.yml GC_COMPOSE_EOF_7f3a
emit .env.example       .env.example       GC_ENV_EOF_7f3a
emit setup.sh           setup.sh           GC_SETUP_EOF_7f3a

cat <<'FTR'
chmod +x setup.sh
printf '\n%s\n' "Wrote: docker-compose.yml, .env.example, setup.sh"
printf '%s\n'   "Next:  ./setup.sh   (generates secrets, creates ./volumes, starts GearCargo)"
FTR
