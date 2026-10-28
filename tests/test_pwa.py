from pathlib import Path


def test_service_worker_and_manifest_are_served_with_expected_types(anonymous_client):
    worker = anonymous_client.get("/sw.js")
    manifest = anonymous_client.get("/manifest.webmanifest")

    assert worker.status_code == 200
    assert worker.headers["content-type"].startswith("application/javascript")
    assert worker.headers["cache-control"] == "no-cache"
    assert manifest.status_code == 200
    assert manifest.headers["content-type"].startswith("application/manifest+json")


def test_manifest_has_installable_fields_and_existing_png_icons(anonymous_client):
    manifest = anonymous_client.get("/manifest.webmanifest").json()
    static_dir = Path(__file__).resolve().parents[1] / "app" / "static"

    assert manifest["name"] == "Origo"
    assert manifest["short_name"]
    assert manifest["start_url"] == "/"
    assert manifest["scope"] == "/"
    assert manifest["display"] == "standalone"
    assert manifest["lang"] == "es-AR"
    assert manifest["theme_color"] and manifest["background_color"]
    assert {icon["sizes"] for icon in manifest["icons"]} >= {"192x192", "512x512"}
    for icon in manifest["icons"]:
        assert icon["type"] == "image/png"
        assert "maskable" in icon["purpose"]
        assert (static_dir / icon["src"].removeprefix("/static/")).is_file()
    assert (static_dir / "icons/icon-180.png").is_file()


def test_csp_is_local_and_offline_page_is_public(anonymous_client):
    csp = anonymous_client.get("/login").headers["content-security-policy"]
    offline = anonymous_client.get("/offline")

    assert "cdn.jsdelivr.net" not in csp
    assert "script-src 'self'" in csp
    assert offline.status_code == 200
    assert "text/html" in offline.headers["content-type"]
    assert "Estás sin conexión" in offline.text
    assert offline.headers["cache-control"] == "no-store"


def test_versioned_static_files_have_immutable_cache_headers(anonymous_client):
    response = anonymous_client.get("/static/app.css?v=test-version")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "public, max-age=31536000, immutable"


def test_gzip_is_enabled_for_html(anonymous_client):
    response = anonymous_client.get("/offline", headers={"accept-encoding": "gzip"})
    assert response.headers.get("content-encoding") == "gzip"


def test_chart_is_loaded_only_on_the_weight_page(client):
    assert "chart-4.4.7.umd.min.js" not in client.get("/plata").text
    assert "chart-4.4.7.umd.min.js" in client.get("/cuerpo").text


def test_worker_precaches_versioned_static_assets_without_html_cache():
    from app.main import _service_worker

    worker = _service_worker()
    assert '"/static/app.css?v=' in worker
    assert '"/static/vendor/htmx-2.0.4.min.js?v=' in worker
    assert 'request.mode === "navigate"' in worker
    assert "cache.put(request" in worker
    assert "url.pathname === \"/login\"" in worker
    assert "url.pathname.startsWith(\"/g/\")" in worker
