# crontab for image building
MAILTO="DISTRO-sysadmin@collabora.co.uk"
PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"

# min        hour         day mon wday user     cmd
15           19           *   *   *    mom      /usr/lib/merge-o-matic/merge-o-matic-run > /dev/null
