import imaplib
import getpass
import sys
import email
import os
import re
import concurrent.futures
import io
import gzip
import logging
import traceback

# Configurar logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

def get_mailbox_name(mailbox_string):
    """Extracts the mailbox name from a mailbox string."""
    logging.debug(f"Analyzing mailbox string: {mailbox_string}")
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

    except (FileNotFoundError, ValueError) as e:
        logging.error(f"Error reading config file: {str(e)}")
        print("Invalid 'emails.txt' file format. The file should have the following format:")
        print("debug=true/false")
        print("source1_server,source1_email,source1_password;destination1_server,destination1_email,destination1_password")
        print("source2_server,source2_email,source2_password;destination2_server,destination2_email,destination2_password")
        print("...")
        sys.exit(1)

def create_mailbox(imap, mailbox_name):
    """Creates a mailbox on the destination server if it doesn't exist."""
    try:
        imap.create(mailbox_name)
        imap.subscribe(mailbox_name)
        logging.info(f"Mailbox created and subscribed: {mailbox_name}")
    except imaplib.IMAP4.error as e:
        logging.error(f"Could not create or subscribe to mailbox {mailbox_name}: {e}")

def migrate_emails(src_server, src_email, src_password, dst_server, dst_email, dst_password, debug_mode):
    """Migrates emails from the source server to the destination server."""
    logging.info("Starting migration process...")

    try:
        # Connect to the source server
        logging.info(f"Connecting to source server: {src_server}")
        src_imap = imaplib.IMAP4_SSL(src_server)
        src_imap.login(src_email, src_password)
        if debug_mode:
            src_imap.debug = 4
        logging.info("Successful connection to source server.")

        # Connect to the destination server
        logging.info(f"Connecting to destination server: {dst_server}")
        dst_imap = imaplib.IMAP4_SSL(dst_server)
        dst_imap.login(dst_email, dst_password)
        if debug_mode:
            dst_imap.debug = 4
        logging.info("Successful connection to destination server.")

        # Get the list of mailboxes from the source server
        status, mailboxes = src_imap.list()
        if status != 'OK':
            logging.error("Error getting the list of mailboxes from the source server.")
            return

        # Process mailboxes sequentially for better error handling
        for mailbox in mailboxes:
            mailbox_name = get_mailbox_name(mailbox.decode())
            try:
                process_mailbox(src_imap, dst_imap, mailbox_name, debug_mode)
            except Exception as e:
                logging.error(f"Error processing mailbox {mailbox_name}: {str(e)}")
                logging.debug(traceback.format_exc())

        logging.info("Migration process finished.")

    except imaplib.IMAP4.error as e:
        logging.error(f"IMAP error: {e}")
    except Exception as e:
        logging.error(f"Unexpected error: {e}")
        logging.debug(traceback.format_exc())
    finally:
        # Close connections
        try:
            src_imap.logout()
            dst_imap.logout()
        except:
            pass

def process_mailbox(src_imap, dst_imap, mailbox_name, debug_mode):
    """Process a single mailbox."""
    logging.info(f"Processing mailbox: {mailbox_name}")

    # Select the source mailbox
    for name_format in [mailbox_name, f'"{mailbox_name}"', f'INBOX.{mailbox_name}', f'"INBOX.{mailbox_name}"']:
        try:
            status, messages = src_imap.select(name_format, readonly=True)
            if status == 'OK':
                logging.info(f"Mailbox successfully selected: {name_format}")
                break
        except Exception as e:
            logging.error(f"Error selecting {name_format}: {e}")
    else:
        logging.warning(f"Could not select mailbox {mailbox_name}. Skipping...")
        return

    # Create the mailbox on the destination server
    create_mailbox(dst_imap, mailbox_name)

    # Search for all messages
    status, messages = src_imap.search(None, 'ALL')
    if status != 'OK':
        logging.error(f"Error searching for messages in {mailbox_name}")
        return

    # Process messages in batches
    batch_size = 100
    message_nums = messages[0].split()
    for i in range(0, len(message_nums), batch_size):
        batch = message_nums[i:i+batch_size]
        process_message_batch(src_imap, dst_imap, mailbox_name, batch, debug_mode)

def process_message_batch(src_imap, dst_imap, mailbox_name, batch, debug_mode):
    """Process a batch of messages."""
    messages_data = []
    for num in batch:
        try:
            # Get the message flags
            status, data = src_imap.fetch(num, '(FLAGS)')
            if status != 'OK':
                logging.error(f"Error getting the flags of message {num} in {mailbox_name}")
                continue
            flags = imaplib.ParseFlags(data[0])
            flags_str = ' '.join([str(f).replace("b'\\", "").replace("'", "") for f in flags])

            # Get the full message
            status, msg_data = src_imap.fetch(num, '(RFC822)')
            if status != 'OK':
                logging.error(f"Error getting message {num} from mailbox {mailbox_name}")
                continue

            # Compress the message data
            compressed_data = gzip.compress(msg_data[0][1])
            messages_data.append((compressed_data, flags_str))
        except Exception as e:
            logging.error(f"Error processing message {num} in {mailbox_name}: {str(e)}")
            if debug_mode:
                logging.debug(traceback.format_exc())

    # Use APPEND to add messages
    try:
        dst_imap.select(mailbox_name)
        for compressed_data, flags_str in messages_data:
            # Decompress the data before appending
            decompressed_data = gzip.decompress(compressed_data)
            dst_imap.append(mailbox_name, f"({flags_str})", None, decompressed_data)
        logging.info(f"Batch of {len(messages_data)} messages migrated to mailbox {mailbox_name}")
    except Exception as e:
        logging.error(f"Error saving batch to mailbox {mailbox_name}: {str(e)}")
        if debug_mode:
            logging.debug(traceback.format_exc())

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