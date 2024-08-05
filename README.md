# Multi Email Migrator

This Python script migrates emails from multiple IMAP accounts to multiple destinations, preserving the read/unread status of the messages.

## Features

* Migrates emails from multiple source accounts to multiple destination accounts.
* Preserves the read/unread status of the messages.
* Supports multiple mailboxes per account.
* Configurable debug mode for detailed output.

## Requirements

* Python 3.x
* `imaplib` module
* `email` module

## Usage

1. Create a configuration file named `emails.txt` with the following format:
debug=true/false
source1_server,source1_email,source1_password;destination1_server,destination1_email,destination1_password
source2_server,source2_email,source2_password;destination2_server,destination2_email,destination2_password
...
* Each line after `debug=true/false` represents a migration.
* Source and destination server data are separated by a semicolon (`;`).
* Server data (server, email, password) are separated by commas (`,`).

2. Run the script:

````
python imap_migrator.py
````

## Configuration

debug=true/false: Enables or disables IMAP debugging output.

### Example Configuration

````
debug=true
imap.example.com,source@example.com,source_password;imap.another.com,destination@another.com,destination_password
imap.example2.com,source@example2.com,source_password2;imap.another2.com,destination@another2.com,destination_password2
````

## Contributing
Contributions are welcome! Please feel free to submit pull requests or open issues.
