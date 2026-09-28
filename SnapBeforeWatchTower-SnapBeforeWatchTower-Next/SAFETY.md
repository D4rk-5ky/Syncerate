# Original project notices

These original notices are preserved from the supplied archive. For the implemented commands and dry-run behavior, see README.md.

## ⚠️ Disclaimer / Liability Notice

**This script is provided “as is”, without warranty of any kind.**  
By using this script, **you agree that I am not liable for any data loss, system damage, service interruption, or other issues** that may occur as a result of running it.

This script performs **destructive operations**, including but not limited to:

- Creating **ZFS snapshots**
- **Destroying ZFS snapshots**
- Deleting log files (`.log`, `.err`, `.digest`)
- Executing system-level commands (`zfs`, `docker`, `mail`)

⚠️ **Always test on a non-production system first.**  
⚠️ **Always ensure you have verified backups.**  
⚠️ **You are fully responsible for reviewing and understanding the code before running it.**

⚠️ AI-assisted / vibe-coded experimental software. Use at your own risk.

## Disclaimer

This project is AI-assisted / vibe-coded software created as a hobby project. It has not been professionally audited and may contain bugs, unsafe behavior, data-loss issues, security problems, or incorrect assumptions.

You are responsible for reviewing the code, testing it in a safe environment, making backups, and understanding what it does before using it on real data. The author is not responsible for damage, data loss, broken systems, security issues, or other problems caused by using this software.

## Data Loss Warning

This application can perform destructive operations, including deleting ZFS snapshots, and backup data. Always test with dry-runs first, check the generated plans, and keep a separate working backup.

## License

No license is implied unless explicitly added.  
Use, modify, and run this script **entirely at your own risk**.
