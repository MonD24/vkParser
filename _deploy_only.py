import paramiko

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect('195.26.226.85', username='root')

sftp = c.open_sftp()
for local, remote in [
    (r'e:\botWim\tg_control.py',      '/opt/botwim/tg_control.py'),
    (r'e:\botWim\contest_parser.py',  '/opt/botwim/contest_parser.py'),
]:
    with open(local, 'rb') as f:
        sftp.putfo(f, remote)
    print(f"Uploaded {local}")
sftp.close()

_, o, _ = c.exec_command('systemctl restart botwim && sleep 4 && journalctl -u botwim -n 8 --no-pager')
print(o.read().decode().strip())
c.close()
print("Done")
