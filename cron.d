# merge-o-matic cron.d file
MAILTO="root@localhost"
PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
LOG="/srv/obs/log/mom.log"

# min        hour         day mon wday user     cmd
15           0           *   *   *    mom      (cd /srv/obs/merge-o-matic/ && /usr/lib/merge-o-matic/main.py) > "$LOG" 2>&1
