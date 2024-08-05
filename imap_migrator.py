import imaplib
import getpass
import sys
import email
import os
import re

def get_mailbox_name(mailbox_string):
    """Extracts the mailbox name from a mailbox string."""
    print(f"Analyzing mailbox string: {mailbox_string}")
    match = re.search(r'"([^"]+)"$', mailbox_string)
    if match:
        return match.group(1)
    else:
        return mailbox_string.split()[-1]

def read_config_file():
    """Reads the configuration data from the 'emails.txt' file."""
    debug_mode = False
    migrations = []

    try:
        with open('emails.txt', 'r') as f:
            for line in f:
                line = line.strip()
                if line.startswith('debug='):
                    debug_mode = line.split('=')[1].lower() == 'true'
                else:
                    source, destination = line.split(';')
                    source_data = source.split(',')
                    destination_data = destination.split(',')

                    # Validate that each section has 3 elements
                    if len(source_data) != 3 or len(destination_data) != 3:
                        raise ValueError("Invalid format")

                    migrations.append((source_data, destination_data))

        return debug_mode, migrations

    except (FileNotFoundError, ValueError):
        print("Invalid 'emails.txt' file format. The file should have the following format:")
        print("debug=true/false")
        print("source1_server,source1_email,source1_password;destination1_server,destination1_email,destination1_password")
        print("source2_server,source2_email,source2_password;destination2_server,destination2_email,destination2_password")
        print("...")
        sys.exit(1)

def get_input(prompt, config_value):
    """Gets input from the user, using a default value if provided."""
    if config_value:
        print(f"{prompt} {config_value}")
        return config_value
    return input(prompt)

def get_password(prompt, config_value):
    """Gets a password from the user securely, hiding the input."""
    if config_value:
        print(f"{prompt} [Hidden password]")
        return config_value
    return getpass.getpass(prompt)

def create_mailbox(imap, mailbox_name):
    """Creates a mailbox on the destination server if it doesn't exist."""
    try:
        imap.create(mailbox_name)
        imap.subscribe(mailbox_name)
        print(f"Mailbox created and subscribed: {mailbox_name}")
    except imaplib.IMAP4.error as e:
        print(f"Could not create or subscribe to mailbox {mailbox_name}: {e}")

def migrate_emails(src_server, src_email, src_password, dst_server, dst_email, dst_password, debug_mode):
    """Migrates emails from the source server to the destination server."""
    print("Starting migration process...")

    try:
        # Connect to the source server
        print(f"Connecting to source server: {src_server}")
        src_imap = imaplib.IMAP4_SSL(src_server)
        src_imap.login(src_email, src_password)
        if debug_mode:
            src_imap.debug = 4  # Enable debugging for the source server
        print("Successful connection to source server.")

        # Connect to the destination server
        print(f"Connecting to destination server: {dst_server}")
        dst_imap = imaplib.IMAP4_SSL(dst_server)
        dst_imap.login(dst_email, dst_password)
        if debug_mode:
            dst_imap.debug = 4  # Enable debugging for the destination server
        print("Successful connection to destination server.")

        # Get the list of mailboxes from the source server
        status, mailboxes = src_imap.list()
        if status != 'OK':
            print("Error getting the list of mailboxes from the source server.")
            return

        # Iterate over the mailboxes
        for mailbox in mailboxes:
            mailbox_name = get_mailbox_name(mailbox.decode())
            print(f"Mailbox: {mailbox_name}")

            # Select the source mailbox
            for name_format in [mailbox_name, f'"{mailbox_name}"', f'INBOX.{mailbox_name}', f'"INBOX.{mailbox_name}"']:
                try:
                    status, messages = src_imap.select(name_format, readonly=True)
                    if status == 'OK':
                        print(f"Mailbox successfully selected: {name_format}")
                        break
                except Exception as e:
                    print(f"Error selecting {name_format}: {e}")
            else:
                print(f"Could not select mailbox {mailbox_name}. Skipping...")
                continue

            # Create the mailbox on the destination server
            create_mailbox(dst_imap, mailbox_name)

            # Search for all messages
            status, messages = src_imap.search(None, 'ALL')
            if status != 'OK':
                print(f"Error searching for messages in {mailbox_name}")
                continue

            # Iterate over the messages
            for num in messages[0].split():
                # Get the message flags
                status, data = src_imap.fetch(num, '(FLAGS)')
                if status != 'OK':
                    print(f"Error getting the flags of message {num} in {mailbox_name}")
                    continue
                flags = imaplib.ParseFlags(data[0])
                # Remove special characters from flags_str
                flags_str = ' '.join([str(f).replace("b'\\", "").replace("'", "") for f in flags])

                # Get the message header
                status, data = src_imap.fetch(num, '(RFC822.HEADER)')
                if status == 'OK':
                    # Parse the header with the email library
                    msg = email.message_from_bytes(data[0][1])
                    subject = msg['Subject']

                    # Determine the message status
                    status = 'Read' if str(b'\\Seen') in [str(f) for f in flags] else 'Unread'

                    print(f"  Subject: {subject} - Status: {status}")

                # Get the full message
                status, msg_data = src_imap.fetch(num, '(RFC822)')
                if status != 'OK':
                    print(f"Error getting message {num} from mailbox {mailbox_name}")
                    continue

                # Save the message to the destination server
                try:
                    dst_imap.append(mailbox_name, None, None, msg_data[0][1])

                    # Select the destination mailbox
                    dst_imap.select(mailbox_name)

                    # Search for the last message in the destination mailbox
                    status, data = dst_imap.search(None, 'ALL')
                    if status == 'OK' and data[0]:
                        dst_msg_num = data[0].split()[-1]  # Get the last message

                        # Apply the flags to the last message using STORE
                        if debug_mode:
                            print(f"  Applying flags: {flags_str}")
                        dst_imap.store(dst_msg_num, '+FLAGS', f"({flags_str})")

                    print(f"  Message {num} migrated to mailbox {mailbox_name}")
                except Exception as e:
                    print(f"  Error saving message {num} to mailbox {mailbox_name}: {e}")

            print(f"Migration complete for mailbox: {mailbox_name}")

        print("Migration process finished.")

    except imaplib.IMAP4.error as e:
        print(f"IMAP error: {e}")
    except Exception as e:
        print(f"Unexpected error: {e}")
    finally:
        # Close connections
        try:
            src_imap.logout()
            dst_imap.logout()
        except:
            pass


def main():
    """Main function of the script."""
    print("Email migration program")

    debug_mode, migrations = read_config_file()

    for source_data, destination_data in migrations:
        src_server, src_email, src_password = source_data
        dst_server, dst_email, dst_password = destination_data

        # Start migration
        migrate_emails(src_server, src_email, src_password, dst_server, dst_email, dst_password, debug_mode)

if __name__ == "__main__":
    main()
