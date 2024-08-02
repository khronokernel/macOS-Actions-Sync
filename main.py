
import argparse
import macos_sync.sync

if __name__ == "__main__":

    # Parse arguments
    parser = argparse.ArgumentParser(description='Sync macOS settings')
    parser.add_argument('--access_key', type=str, help='Internet Archive access key')
    parser.add_argument('--secret_key', type=str, help='Internet Archive secret key')

    args = parser.parse_args()

    macos_sync.sync.macOSSync(
        access_key=args.access_key,
        secret_key=args.secret_key
    ).iterate_catalog()