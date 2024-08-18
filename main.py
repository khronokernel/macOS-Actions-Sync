
import argparse
import macos_sync.sync

if __name__ == "__main__":

    # Parse arguments
    parser = argparse.ArgumentParser(description='Sync macOS settings')
    parser.add_argument('--access_key',     type=str, help='Internet Archive access key')
    parser.add_argument('--secret_key',     type=str, help='Internet Archive secret key')
    parser.add_argument('--variant',        type=str, help='AppleDB IPSW vs SUCatalog backup', default='AppleDB IPSW')
    parser.add_argument('--target_version', type=str, help='Target version for IPSW backup',   default=None)

    args = parser.parse_args()

    sync_obj = macos_sync.sync.macOSSync(
        access_key=args.access_key,
        secret_key=args.secret_key,
        target_version=args.target_version
    )
    if args.variant == 'AppleDB IPSW':
        sync_obj.iterate_apple_db()
    elif args.variant == 'SUCatalog':
        sync_obj.iterate_catalog()
    else:
        raise ValueError(f'Unknown variant: {args.variant}')