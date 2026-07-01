FROM postgres:15

WORKDIR /backup

COPY backup.sh /backup/backup.sh
RUN chmod +x /backup/backup.sh

ENV BACKUP_DIR=/backups
ENV BACKUP_INTERVAL_SECONDS=300

CMD ["/backup/backup.sh"]
