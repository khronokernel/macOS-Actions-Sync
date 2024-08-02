"""
Goal is to download a single macOS installer and upload to archive.org
"""

import time
import internetarchive

from . import sucatalog, integrity_verification
from .network import download, human_fmt


class macOSSync:

    def __init__(self, access_key: str, secret_key: str) -> None:
        self._access_key  = access_key
        self._secret_key  = secret_key

        self._contributor = "khronokernel"
        self._collection  = "open_source_software"


    def latest_fetch_catalog(self) -> list:
        contents = sucatalog.CatalogURL().url_contents
        return sucatalog.CatalogProducts(contents).products


    def fetch_all_catalogs(self) -> list:
        print("Fetching all catalogs")
        catalog = []
        for version in sucatalog.CatalogVersion:
            if float(version.value) < 11.0:
                break
            for variant in sucatalog.SeedType:
                print(f"  Fetching {version.name.lower().replace('_', ' ').title()} {variant.name}")
                url = sucatalog.CatalogURL(version, variant)
                catalog.extend(sucatalog.CatalogProducts(url.url_contents).products)

        # Deduplicate
        catalog = list({product['Build']: product for product in catalog}.values())

        return catalog


    def is_installer_already_uploaded(self, build: str, type: str = "InstallAssistant.pkg") -> bool:
        search = internetarchive.search_items(f"uploader:{self._contributor} title:({build} AND {type})").iter_as_items()

        # Ensure we don't accidentally get a partial match
        checks = [
            f"({build})",
            f" {build} ",
            f" {build})"
        ]

        for result in search:
            title = result.metadata['title']
            for check in checks:
                if check in title:
                    return True

        return False


    def iterate_catalog(self):
        for product in self.fetch_all_catalogs():
            build = product['Build']
            name = f"{product['Title']} {product['Version']} ({product['Build']})"
            print(f"Checking {name}")
            if self.is_installer_already_uploaded(build):
                print(f"  {build} already uploaded, skipping")
                continue

            print(f"  {name} not uploaded, downloading")
            print(f"  Downloading {name} InstallAssistant.pkg")

            download_obj = download.DownloadObject(product["InstallAssistant"]["URL"], "InstallAssistant.pkg")
            download_obj.download()
            while download_obj.is_active():
                print(f"    Percentage downloaded: {download_obj.get_percent():.2f}%", end="\r")
                time.sleep(5)

            if not download_obj.download_complete:
                print("")
                print(f"Failed to download {build}")
                print(f"URL: {product['InstallAssistant']['URL']}")
                raise Exception(f"Failed to download {build}")

            print("    Percentage downloaded: 100.00%")
            print(f"    Time elapsed: {(time.time() - download_obj.start_time):.2f} seconds")
            print(f"    Speed: {human_fmt(download_obj.downloaded_file_size / (time.time() - download_obj.start_time))}/s")

            print(f"  Downloading {name} InstallAssistant.pkg.integrityDataV1")

            download_obj = download.DownloadObject(product["InstallAssistant"]["IntegrityDataURL"], "InstallAssistant.pkg.integrityDataV1")
            download_obj.download()
            while download_obj.is_active():
                print(f"    Percentage downloaded: {download_obj.get_percent():.2f}%", end="\r")
                time.sleep(5)

            if not download_obj.download_complete:
                print("")
                print(f"Failed to download {build}")
                print(f"URL: {product['InstallAssistant']['IntegrityDataURL']}")
                raise Exception(f"Failed to download {build}")

            print("    Percentage downloaded: 100.00%")
            print(f"    Time elapsed: {(time.time() - download_obj.start_time):.2f} seconds")
            print(f"    Speed: {human_fmt(download_obj.downloaded_file_size / (time.time() - download_obj.start_time))}/s")


            print(f"  Verifying {name} InstallAssistant.pkg")

            chunk_obj = integrity_verification.ChunklistVerification("InstallAssistant.pkg", "InstallAssistant.pkg.integrityDataV1")
            chunk_obj.validate()

            while chunk_obj.status == integrity_verification.ChunklistStatus.IN_PROGRESS:
                print(f"    Validating {chunk_obj.current_chunk} of {chunk_obj.total_chunks}")
                time.sleep(5)

            if chunk_obj.status == integrity_verification.ChunklistStatus.FAILURE:
                print(chunk_obj.error_msg)
                raise Exception(f"Failed to validate {build}")


            # upload to archive.org
            files = [
                "InstallAssistant.pkg",
                "InstallAssistant.pkg.integrityDataV1"
            ]

            item = internetarchive.upload(
                identifier=f"macOS-{product['Build']}-InstallAssistant",
                files=files,
                metadata={
                    'collection': self._collection,
                    'title':      f"{product['Title']} {product['Version']} ({product['Build']}) InstallAssistant.pkg",
                    'mediatype':  'software'
                },
                access_key=self._access_key,
                secret_key=self._secret_key,
            )

            print(f"  {build} uploaded")

            # Only upload one installer at a time
            return



