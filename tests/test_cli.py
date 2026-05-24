import csv
import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from site_exif.cli import (
    FetchResult,
    SiteHTMLParser,
    extract_css_urls,
    extract_jpeg_exif,
    extract_metadata,
    extract_pdf_metadata,
    extract_png_metadata,
    extract_sitemap_urls,
    extract_text_urls,
    host_matches,
    is_xml_content_type,
    normalize_candidate,
    main,
    parse_srcset,
)


def tiff_with_make(make: bytes = b"Canon\x00") -> bytes:
    return (
        b"II"
        + (42).to_bytes(2, "little")
        + (8).to_bytes(4, "little")
        + (1).to_bytes(2, "little")
        + (0x010F).to_bytes(2, "little")
        + (2).to_bytes(2, "little")
        + len(make).to_bytes(4, "little")
        + (26).to_bytes(4, "little")
        + (0).to_bytes(4, "little")
        + make
    )


class UrlTests(unittest.TestCase):
    def test_normalize_candidate_skips_non_http_links(self):
        self.assertIsNone(normalize_candidate("https://example.com", "mailto:a@example.com"))
        self.assertIsNone(normalize_candidate("https://example.com", "data:image/png;base64,abc"))

    def test_normalize_candidate_rejects_markup_fragments(self):
        self.assertIsNone(
            normalize_candidate(
                "https://chelseafiler.com/sitemap.xml",
                "https://chelseafiler.com/?<link>https://chelseafiler.com</link>",
            )
        )

    def test_normalize_candidate_resolves_relative_url(self):
        self.assertEqual(
            normalize_candidate("https://example.com/a/b/index.html", "../img/photo.jpg#x"),
            "https://example.com/a/img/photo.jpg",
        )

    def test_normalize_candidate_quotes_valid_paths_with_spaces(self):
        self.assertEqual(
            normalize_candidate("https://example.com/gallery/", "./Blue Ridge Wilderness Therapy (1).jpg"),
            "https://example.com/gallery/Blue%20Ridge%20Wilderness%20Therapy%20(1).jpg",
        )

    def test_normalize_candidate_rejects_bare_human_filenames_with_spaces(self):
        self.assertIsNone(normalize_candidate("https://example.com/gallery/", "Blue Ridge Wilderness Blog.png"))

    def test_host_matching_can_include_subdomains(self):
        self.assertTrue(host_matches("www.example.com", "assets.example.com", True))
        self.assertFalse(host_matches("www.example.com", "assets.example.com", False))

    def test_srcset_parser_returns_urls_only(self):
        self.assertEqual(parse_srcset("small.jpg 1x, large.jpg 2x"), ["small.jpg", "large.jpg"])

    def test_srcset_parser_preserves_filenames_with_spaces(self):
        self.assertEqual(
            parse_srcset("/uploads/Blue Ridge Wilderness Blog.png 600w, /uploads/Screen Shot 2022.png 2x"),
            ["/uploads/Blue Ridge Wilderness Blog.png", "/uploads/Screen Shot 2022.png"],
        )

    def test_html_parser_finds_lazy_loaded_media(self):
        parser = SiteHTMLParser("https://example.com/gallery/")
        parser.feed(
            '<img data-src="/lazy.jpg">'
            '<div style="background-image: url(/hero.webp)"></div>'
            '<source data-srcset="/small.jpg 1x, /large.jpg 2x">'
        )
        self.assertIn("https://example.com/lazy.jpg", parser.links)
        self.assertIn("https://example.com/hero.webp", parser.links)
        self.assertIn("https://example.com/large.jpg", parser.links)

    def test_html_parser_finds_srcset_media_with_spaces(self):
        parser = SiteHTMLParser("https://example.com/gallery/")
        parser.feed('<img srcset="/uploads/Blue Ridge Wilderness Blog.png 600w">')
        self.assertIn("https://example.com/uploads/Blue%20Ridge%20Wilderness%20Blog.png", parser.links)

    def test_css_url_extraction_preserves_quoted_spaces(self):
        urls = extract_css_urls("https://example.com/css/page.css", 'body { background: url("/uploads/Screen Shot 2022.png"); }')
        self.assertEqual(urls, {"https://example.com/uploads/Screen%20Shot%202022.png"})

    def test_text_url_extraction_finds_script_embedded_media(self):
        urls = extract_text_urls("https://example.com", 'const img = "/uploads/photo.jpg";')
        self.assertIn("https://example.com/uploads/photo.jpg", urls)

    def test_text_url_extraction_ignores_bare_human_filenames(self):
        urls = extract_text_urls("https://example.com", '"Blue Ridge Wilderness Blog.png"')
        self.assertEqual(urls, set())

    def test_sitemap_extraction_finds_loc_urls(self):
        sitemap = b'<?xml version="1.0"?><urlset><url><loc>https://example.com/page</loc></url></urlset>'
        self.assertEqual(extract_sitemap_urls("https://example.com/sitemap.xml", sitemap), {"https://example.com/page"})

    def test_text_url_extraction_rejects_xml_fragment_url(self):
        text = "https://chelseafiler.com/?<link>https://chelseafiler.com</link>"
        self.assertEqual(extract_text_urls("https://chelseafiler.com/sitemap.xml", text), {"https://chelseafiler.com/"})

    def test_rss_content_type_is_xml(self):
        self.assertTrue(is_xml_content_type("application/rss+xml"))


class MetadataTests(unittest.TestCase):
    def test_png_text_metadata(self):
        chunk_data = b"Author\x00Jane Doe"
        chunk = len(chunk_data).to_bytes(4, "big") + b"tEXt" + chunk_data + b"\x00\x00\x00\x00"
        png = b"\x89PNG\r\n\x1a\n" + chunk
        self.assertEqual(extract_png_metadata(png), [("png", "Author", "Jane Doe")])

    def test_pdf_info_metadata(self):
        pdf = b"%PDF-1.4\n1 0 obj << /Title (Audit Report) /Author (Jane Doe) >> endobj"
        self.assertIn(("pdf", "Title", "Audit Report"), extract_pdf_metadata(pdf))
        self.assertIn(("pdf", "Author", "Jane Doe"), extract_pdf_metadata(pdf))

    def test_jpeg_exif_metadata(self):
        segment = b"Exif\x00\x00" + tiff_with_make()
        jpeg = b"\xff\xd8\xff\xe1" + (len(segment) + 2).to_bytes(2, "big") + segment + b"\xff\xd9"
        self.assertIn(("exif", "Make", "Canon"), extract_jpeg_exif(jpeg))

    def test_png_exif_chunk_metadata(self):
        chunk_data = tiff_with_make(b"Nikon\x00")
        chunk = len(chunk_data).to_bytes(4, "big") + b"eXIf" + chunk_data + b"\x00\x00\x00\x00"
        png = b"\x89PNG\r\n\x1a\n" + chunk
        self.assertIn(("exif", "Make", "Nikon"), extract_png_metadata(png))

    def test_webp_exif_metadata(self):
        chunk_data = tiff_with_make(b"Sony\x00")
        webp = b"RIFF" + (len(chunk_data) + 12).to_bytes(4, "little") + b"WEBP" + b"EXIF" + len(chunk_data).to_bytes(4, "little") + chunk_data
        self.assertIn(("exif", "Make", "Sony"), extract_metadata("https://example.com/photo.webp", "image/webp", webp))


class CrawlTests(unittest.TestCase):
    def test_crawl_writes_discovered_asset_metadata(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            chunk_data = b"Author\x00Jane Doe"
            chunk = len(chunk_data).to_bytes(4, "big") + b"tEXt" + chunk_data + b"\x00\x00\x00\x00"
            png = b"\x89PNG\r\n\x1a\n" + chunk
            output = root / "metadata.csv"

            def fake_fetch(url, *_args):
                if url.endswith("/index.html"):
                    return FetchResult(url, "text/html", b'<html><body><img src="/photo.png"></body></html>')
                return FetchResult(url, "image/png", png)

            with mock.patch("site_exif.cli.fetch_url", side_effect=fake_fetch):
                code = main(
                    [
                        "crawl",
                        "https://example.com/index.html",
                        "--output",
                        str(output),
                        "--max-pages",
                        "5",
                        "--no-sitemaps",
                    ]
                )

            self.assertEqual(code, 0)
            with output.open(newline="", encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(len(rows), 1)
            self.assertIn("png_Author", rows[0])
            self.assertEqual(rows[0]["png_Author"], "Jane Doe")

    def test_crawl_does_not_fetch_malformed_markup_urls(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            output = root / "metadata.csv"
            fetched_urls = []

            def fake_fetch(url, *_args):
                fetched_urls.append(url)
                return FetchResult(
                    url,
                    "text/html",
                    b'<html><body>https://example.com/?<link>https://example.com/photo.png</link></body></html>',
                )

            with mock.patch("site_exif.cli.fetch_url", side_effect=fake_fetch):
                code = main(
                    [
                        "crawl",
                        "https://example.com/index.html",
                        "--output",
                        str(output),
                        "--max-pages",
                        "1",
                        "--no-sitemaps",
                    ]
                )

            self.assertEqual(code, 0)
            self.assertNotIn("https://example.com/?<link>https://example.com/photo.png</link>", fetched_urls)

    def test_interactive_builds_crawl_args_from_prompts(self):
        answers = [
            "https://example.com",
            "out.csv",
            "y",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
        ]
        with mock.patch("builtins.input", side_effect=answers):
            with mock.patch("site_exif.cli.crawl", return_value=0) as crawl_mock:
                with contextlib.redirect_stdout(io.StringIO()):
                    code = main(["interactive"])

        self.assertEqual(code, 0)
        crawl_args = crawl_mock.call_args.args[0]
        self.assertEqual(crawl_args.url, "https://example.com")
        self.assertEqual(crawl_args.output, "out.csv")
        self.assertEqual(crawl_args.max_pages, 0)
        self.assertEqual(crawl_args.max_depth, -1)
        self.assertTrue(crawl_args.verbose)


if __name__ == "__main__":
    unittest.main()
