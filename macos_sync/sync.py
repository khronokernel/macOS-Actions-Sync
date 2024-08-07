"""
Goal is to download a single macOS installer and upload to archive.org
"""

import time
import internetarchive

from pathlib import Path

from . import sucatalog, integrity_verification
from .network import download, human_fmt, NetworkUtilities


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


    def download_item(self, url: str) -> None:
        name = Path(url).name
        print(f"  Downloading {name}")

        # Check if URL is 404
        if NetworkUtilities(url).validate_link() is False:
            print(f"    {url} is a 404")
            raise Exception(f"{url} is a 404")

        download_obj = download.DownloadObject(url, name)
        download_obj.download()
        while download_obj.is_active():
            print(f"    Percentage downloaded: {download_obj.get_percent():.2f}%", end="\r")
            time.sleep(5)

        if not download_obj.download_complete:
            print("")
            print(f"Failed to download {name}")
            print(f"URL: {url}")
            raise Exception(f"Failed to download {name}")

        # Check if we downloaded an HTML file
        if not name.endswith("html"):
            # Check if content starts with '<!DOCTYPE html>'
            with open(name, "r") as f:
                if f.read(15) == "<!DOCTYPE html>":
                    print(f"    {url} is a 404")
                    raise Exception(f"{url} is a 404")

        print("    Percentage downloaded: 100.00%")
        print(f"    Time elapsed: {(time.time() - download_obj.start_time):.2f} seconds")
        print(f"    Speed: {human_fmt(download_obj.downloaded_file_size / (time.time() - download_obj.start_time))}/s")


    def verify_integrity(self, file: str, integrity_file: str) -> None:
        chunk_obj = integrity_verification.ChunklistVerification(file, integrity_file)
        chunk_obj.validate()

        while chunk_obj.status == integrity_verification.ChunklistStatus.IN_PROGRESS:
            print(f"    Validating {chunk_obj.current_chunk} of {chunk_obj.total_chunks}")
            time.sleep(5)

        if chunk_obj.status == integrity_verification.ChunklistStatus.FAILURE:
            print(chunk_obj.error_msg)
            raise Exception(f"Failed to validate {Path(file).name}")


    def generate_description(self, files: list, urls: list, post_date: str, product_id: str = None, catalog: str = None) -> str:
        description = ""
        description += "Files:\n"

        for file in files:
            description += f"- {file}\n"
        description += "\n"

        description += "Original URLs:\n"
        for url in urls:
            description += f"- {url}\n"
        description += "\n"

        description += f"Original Post Date: {post_date}\n"
        description += "\n"

        if product_id:
            description += f"Original Product ID: {product_id}\n"
            description += "\n"

        if catalog:
            description += f"Original Catalog: {catalog}\n"
            description += "\n"

        description += "Uploaded automatically by https://github.com/khronokernel/macOS-Actions-Sync"

        return description


    def iterate_catalog(self):
        for product in self.fetch_all_catalogs():
            build = product['Build']
            name = f"{product['Title']} {product['Version']} ({product['Build']})"

            print(f"Checking {name}")
            if self.is_installer_already_uploaded(build, "InstallAssistant.pkg"):
                print(f"  {build} already uploaded, skipping")
                continue

            print(f"  {name} not uploaded, downloading")

            self.download_item(product['InstallAssistant']['URL'])
            self.download_item(product['InstallAssistant']['IntegrityDataURL'])

            print(f"  Verifying {name} InstallAssistant.pkg")
            self.verify_integrity("InstallAssistant.pkg", "InstallAssistant.pkg.integrityDataV1")

            # upload to archive.org
            files = [
                "InstallAssistant.pkg",
                "InstallAssistant.pkg.integrityDataV1"
            ]

            responses = internetarchive.upload(
                identifier=f"macOS-{product['Build']}-InstallAssistant",
                files=files,
                metadata={
                    'collection': self._collection,
                    'title':      f"{product['Title']} {product['Version']} ({product['Build']}) InstallAssistant.pkg",
                    'mediatype':  'software',
                    'description': self.generate_description(files, [product['InstallAssistant']['URL'], product['InstallAssistant']['IntegrityDataURL']], product['PostDate'], product['ProductID'], product['Catalog'].name),
                },
                access_key=self._access_key,
                secret_key=self._secret_key,
            )

            for response in responses:
                if response.status_code != 200:
                    print(f"Failed to upload {build}")
                    print(response.text)
                    raise Exception(f"Failed to upload {build}")


            print(f"  {build} uploaded")

            # Only upload one installer at a time
            return


    def fetch_apple_db_items(self) -> dict:
        """
        Get macOS installers from AppleDB
        """

        variant = ".ipsw"

        installers = [
            # "22F82": {
            #   url: "https://swcdn.apple.com/content/downloads/36/06/042-01917-A_B57IOY75IU/oocuh8ap7y8l8vhu6ria5aqk7edd262orj/InstallAssistant.pkg",
            #   version: "13.4.1",
            #   build: "22F82",
            # }
        ]

        print(f"APPLEDB: Getting installers for variant: {variant}")

        apple_db = NetworkUtilities().get("https://api.appledb.dev/main.json")
        if apple_db is None:
            return installers

        apple_db = apple_db.json()
        for group in apple_db:
            if group != "ios":
                continue
            for item in apple_db[group]:
                if "osStr" not in item:
                    continue
                if item["osStr"] != "macOS":
                    continue
                if "build" not in item:
                    continue
                if "version" not in item:
                    continue
                if "sources" not in item:
                    continue
                for source in item["sources"]:
                    if "links" not in source:
                        continue

                    hash = None
                    if "hashes" in source:
                        if "sha1" in source["hashes"]:
                            hash = source["hashes"]["sha1"]

                    for entry in source["links"]:
                        if "url" not in entry:
                            continue
                        if entry["url"].endswith(variant) is False:
                            continue
                        if "preferred" in entry:
                            if entry["preferred"] is False:
                                continue

                        installers.append({
                            "Version":   item["version"],
                            "Build":     item["build"],
                            "URL":       entry["url"],
                            "Variant":   "Beta" if item["beta"] else "Public",
                            "Date":      item["released"],
                            "Hash":      hash,
                        })

        # Deduplicate builds
        installers = list({installer['Build']: installer for installer in installers}.values())

        # reverse list
        installers = installers[::-1]

        return installers


    def iterate_apple_db(self):
        """
        Fetch IPSWs
        """
        known_bad_builds = [
            "20A5299w",
            "20A5323l"
        ]

        for installer in self.fetch_apple_db_items():
            build = installer['Build']
            name = f"macOS {installer['Version']} ({build})"

            if build in known_bad_builds:
                continue

            print(f"Checking {name}")
            if self.is_installer_already_uploaded(build, "UniversalMac.ipsw"):
                print(f"  {build} already uploaded, skipping")
                continue

            print(f"  {name} not uploaded, downloading")
            file_name = Path(installer['URL']).name
            self.download_item(installer['URL'])

            # Compare hash if available
            if installer['Hash']:
                print(f"  Verifying {name} UniversalMac.ipsw")
                import hashlib
                sha1 = hashlib.sha1()
                with open(file_name, "rb") as f:
                    while True:
                        data = f.read(65536)
                        if not data:
                            break
                        sha1.update(data)

                if sha1.hexdigest() != installer['Hash']:
                    print(f"  Hash mismatch for {name}")
                    print(f"  Expected: {installer['Hash']}")
                    print(f"  Got:      {sha1.hexdigest()}")
                    raise Exception(f"Hash mismatch for {name}")

                print(f"  Hash verified")

            # upload to archive.org
            files = [file_name]

            responses = internetarchive.upload(
                identifier=f"macOS-{build}-UniversalMac",
                files=files,
                metadata={
                    'collection': self._collection,
                    'title':      f"{name} UniversalMac.ipsw",
                    'mediatype':  'software',
                    'description': self.generate_description(files, [installer['URL']], installer['Date']),
                },
                access_key=self._access_key,
                secret_key=self._secret_key,
            )

            for response in responses:
                if response.status_code != 200:
                    print(f"Failed to upload {build}")
                    print(response.text)
                    raise Exception(f"Failed to upload {build}")

            print(f"  {build} uploaded")

            # Only upload one installer at a time
            return