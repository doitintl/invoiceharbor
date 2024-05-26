import argparse
import csv
import os
import re
import shutil
import sys


def copy_files(csv_file='invoices-test.csv', source_dir=None, target_dir='data/test-invoices'):
    if source_dir is None:
        print("Please provide a source directory.")
        sys.exit(1)

    if os.path.exists(target_dir):
        if os.listdir(target_dir):  # directory is not empty
            print("Target directory is not empty. Please delete the target directory and try again.")
            sys.exit(1)
    else:
        os.makedirs(target_dir)  # create target directory if it doesn't exist

    with open(csv_file, 'r') as file:
        reader = csv.reader(file)
        next(reader)  # skip header row
        for row in reader:
            file_name = row[0]
            aws_account_number = row[3]
            doit_payer_id = row[1]
            subfolder = f"{aws_account_number}_{doit_payer_id}"
            source_file_path = os.path.join(source_dir, subfolder, file_name)
            target_path = os.path.join(target_dir, subfolder)
            os.makedirs(target_path, exist_ok=True)
            # sometimes the subfolder name is based on different aws_account_number but the same doit_payer_id
            if not os.path.exists(source_file_path):
                # find all subfolder in source_dir ending with doit_payer_id
                subfolders = [f for f in os.listdir(source_dir) if re.search(f"_{doit_payer_id}$", f)]
                # if there is only one subfolder, use that as source
                if len(subfolders) == 1:
                    source_file_path = os.path.join(source_dir, subfolders[0], file_name)
            if os.path.exists(source_file_path):
                try:
                    shutil.copy(source_file_path, target_path)
                    print(f"Copying file from {source_file_path} to {target_path}")
                except IOError as e:
                    print(f"Unable to copy file. {os.strerror(e.errno)}")
                except:
                    print("Unexpected error:", sys.exc_info())
            else:
                print(f"Source file {source_file_path} does not exist.")


def main():
    parser = argparse.ArgumentParser(
        description='Copy files from source directory to target directory based on CSV file.')
    parser.add_argument('--csv', default='invoices-test.csv', help='Path to the CSV file.')
    parser.add_argument('--source', required=True, help='Path to the source directory.')
    parser.add_argument('--target', default='data/test-invoices',
                        help='Path to the target directory. Default is "data/test-invoices".')

    args = parser.parse_args()

    copy_files(csv_file=args.csv, source_dir=args.source, target_dir=args.target)


if __name__ == "__main__":
    main()
