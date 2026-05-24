# Barbie Bitch Cult presents: Domain Metadata Harvester  

Step into the void, darling. While basic bitches are busy screenshotting their iced lattes, this tool is out here crawling an entire domain. Feed it a single URL and watch it slither through every linked page, subdomain, embedded PDF, and thirst-trap image—ripping out the juicy EXIF and metadata like it’s gossip from the group chat. Then it neatly packages the dirt into a CSV because even chaotic queens need spreadsheets.  

Perfect for researchers, investigators, journalists, curious minds, and anyone who understands that the internet never really forgets… it just hides the receipts in the file headers.


# Why EXIF & Metadata Actually Matter

Every photo, PDF, Office doc, and video you upload carries a hidden passenger manifest. That “cute selfie” or “professional headshot” often contains:GPS coordinates (yes, really — your phone helpfully tagged the exact spot you took it)
* Device make/model (iPhone 16 Pro Max, Canon EOS R5, etc.)
* Timestamp (down to the second, including original creation time even if the file was renamed)
* Software used (reveals editing apps, Photoshop versions, even phone apps)
* Camera settings (shutter speed, aperture, ISO — forensic gold for verifying authenticity)
* Author/Owner info (names, company info, emails embedded in PDFs and Office files)
* Thumbnail caches, previous versions, and edit history in many document formats
* Geotags in videos, altitude data, and sometimes even WiFi SSIDs the device was connected to

This data survives screenshots, “save image as,” and most basic stripping attempts. It’s the reason paparazzi can be sued with photos they never touched, the reason OSINT sleuths can map an entire influencer’s travel history, and the reason your “anonymous” leak might not be as anonymous as you thought.In short: your media is snitching on you. This tool just gives you the transcripts. 

This tool is provided "as is" for educational, research, and OSINT purposes only.  Use of this software is at your own risk. The author and Barbie Bitch Cult are not responsible for any misuse, damage, legal consequences, or broken nails that may result from running it.


Welcome to the Cult, bitch.  Now go harvest.




# site-exif

`site-exif` crawls pages under a starting website URL, discovers same-site media and linked documents, extracts available image/document metadata, and writes the result to CSV.

It uses only the Python standard library. No browser, API key, or third-party package is required.

## Beginner Setup

This tool needs Python. Python is free. You do not need to know how to program.

### Windows

1. Open a web browser.
2. Go to <https://www.python.org/downloads/windows/>.
3. Click the newest Python 3 download button.
4. Open the downloaded installer.
5. On the first installer screen, check the box that says **Add python.exe to PATH**.
6. Click **Install Now**.
7. When it finishes, click **Close**.
8. Put this `site-exif` folder somewhere easy to find, such as your Desktop.
9. Open the folder in File Explorer.
10. Click the address bar at the top of File Explorer.
11. Type `cmd` and press Enter. A black Command Prompt window should open already inside this folder.
12. Type this command and press Enter:

```bat
py run_site_exif.py interactive
```

If Windows says `py` is not found, close the Command Prompt, reopen it, and try:

```bat
python run_site_exif.py interactive
```

### macOS

1. Open a web browser.
2. Go to <https://www.python.org/downloads/macos/>.
3. Download the newest Python 3 installer for macOS.
4. Open the downloaded `.pkg` file.
5. Click through the installer using the default choices.
6. Put this `site-exif` folder somewhere easy to find, such as your Desktop.
7. Open the **Terminal** app. You can find it with Spotlight by pressing Command-Space and typing `Terminal`.
8. In Terminal, type `cd ` with a space after it.
9. Drag the `site-exif` folder into the Terminal window. The folder path will appear after `cd`.
10. Press Enter.
11. Type this command and press Enter:

```bash
python3 run_site_exif.py interactive
```

### Linux

From this folder:

```bash
python3 run_site_exif.py interactive
```

Optional Linux command install:

```bash
make install-local
make shell-setup
source ~/.bashrc
```

## Usage

For most people, use interactive mode:

```bash
python3 run_site_exif.py interactive
```

On Windows, use:

```bat
py run_site_exif.py interactive
```

The interactive mode asks questions one at a time and then starts the scan.

Advanced command-line usage:

```bash
site-exif crawl https://example.com --output example-metadata.csv
```

Useful options:

```bash
site-exif crawl https://example.com \
  --output metadata.csv \
  --max-pages 1000 \
  --max-depth 4 \
  --timeout 20 \
  --user-agent "Mozilla/5.0 metadata-audit" \
  --verbose
```

For a full crawl attempt on a large site, remove the limits:

```bash
site-exif crawl https://example.com \
  --output metadata.csv \
  --max-pages 0 \
  --max-depth -1 \
  --verbose
```

By default, the crawler follows the same root domain, including common subdomains such as `www.example.com` and `assets.example.com`. Use `--exact-host` when you only want the exact starting host.

The crawler discovers:

- linked pages from `a href`
- embedded and linked media from `img`, `source`, `video`, `audio`, `embed`, `iframe`, `object`, `link`, and common Open Graph/Twitter meta tags
- lazy-loaded media from common `data-src`, `data-srcset`, `data-lazy-src`, background-image, and related attributes
- media URLs embedded in CSS and JavaScript text
- pages listed in `/sitemap.xml` and sitemap entries from `/robots.txt`
- documents and downloadable assets linked from same-site pages

## CSV Output

Each discovered asset is written as one CSV row. Metadata fields become dynamic CSV columns as they are discovered:

```csv
source_url,page_url,media_type,content_type,file_extension,bytes,error,exif_Make,gps_GPSLatitude,pdf_Author,png_Author
```

For example, a JPEG with GPS EXIF data will add columns such as `gps_GPSLatitude`, `gps_GPSLongitude`, and `gps_GPSAltitude` to the CSV. A file with no supported metadata is still recorded with the fixed columns. Errors are recorded in the `error` column.

## Commands

```bash
site-exif --help
site-exif --json doctor
site-exif interactive
site-exif crawl URL --output metadata.csv
```

`doctor --json` returns a stable JSON object with the Python version and supported extractors.

## Notes

- Respect website terms and robots policies before crawling.
- Keep crawl limits bounded on large sites.
- EXIF extraction is intentionally conservative and covers common JPEG/TIFF EXIF tags, PNG text and EXIF chunks, WebP EXIF chunks, GIF comments, PDF document info, and XMP packets found in supported files.
