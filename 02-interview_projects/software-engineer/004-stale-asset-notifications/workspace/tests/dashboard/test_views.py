import csv
import io

import pytest

from atlas.assets.models import Asset, SavedView
from atlas.dashboard.charts import SEVERITY_ORDER, bar_chart
from atlas.exposure.models import Exposure
from tests import factories

pytestmark = pytest.mark.django_db

XSS = '<script>alert("x")</script>'


def _csv(response):
    return list(csv.reader(io.StringIO(b"".join(response.streaming_content).decode())))


@pytest.mark.parametrize("url", ["/assets/", "/assets.csv", "/assets/1/", "/exposures/", "/ownership/"])
def test_pages_require_login(client, url):
    response = client.get(url)
    assert response.status_code == 302
    assert response["Location"].startswith("/accounts/login/?next=")


def test_login_page_and_home_redirect(client, dashboard_client):
    assert b'name="username"' in client.get("/accounts/login/").content
    response = dashboard_client.get("/")
    assert response.status_code == 302 and response["Location"] == "/assets/"


def test_list_is_scoped_to_current_org(dashboard_client, org, other_org):
    mine = factories.make_asset(org, key="www.harborview-bank.example.test")
    factories.make_asset(other_org, key="cdn.quillstone-media.example.test")
    response = dashboard_client.get("/assets/")
    assert list(response.context["assets"]) == [mine]
    assert b"quillstone" not in response.content


def test_other_orgs_asset_is_404(dashboard_client, other_org):
    theirs = factories.make_asset(other_org)
    assert dashboard_client.get(f"/assets/{theirs.pk}/").status_code == 404


def test_org_switcher_is_limited_to_memberships(client, org, other_org):
    user = factories.make_user("multi", orgs=[org, other_org])
    client.force_login(user)
    theirs = factories.make_asset(other_org)
    response = client.get("/assets/?org=quillstone-media")
    assert list(response.context["assets"]) == [theirs]
    # The choice sticks in the session for later pages, detail included.
    assert client.get(f"/assets/{theirs.pk}/").status_code == 200
    factories.make_org("orchid-grid")
    assert client.get("/assets/?org=orchid-grid").status_code == 404


def test_user_without_membership_gets_404(client, org):
    client.force_login(factories.make_user("nobody"))
    assert client.get("/assets/").status_code == 404


def test_filters_are_applied_and_kept_across_pages(dashboard_client, org):
    for _ in range(51):
        factories.make_asset(org, kind=Asset.Kind.HOST)
    ip = factories.make_asset(org, kind=Asset.Kind.IP, key="203.0.113.10")
    response = dashboard_client.get("/assets/?kind=ip")
    assert list(response.context["assets"]) == [ip]

    response = dashboard_client.get("/assets/?q=example&kind=host")
    assert response.context["paginator"].count == 51
    assert response.context["querystring"] == "kind=host&q=example"
    assert b'href="?kind=host&amp;q=example&amp;page=2"' in response.content
    assert len(dashboard_client.get("/assets/?kind=host&q=example&page=2").context["assets"]) == 1


def test_invalid_filter_shows_error(dashboard_client, org):
    factories.make_asset(org)
    response = dashboard_client.get("/assets/?changed_since=2026-11-01T00:00:00")
    assert response.status_code == 200
    assert list(response.context["assets"]) == []
    assert "changed_since" in response.context["filter_error"]


def test_list_query_count_does_not_grow_with_rows(dashboard_client, org, django_assert_max_num_queries):
    tag = factories.make_tag(org, "pci")
    for _ in range(30):
        asset = factories.make_asset(org)
        asset.tags.add(tag)
        factories.make_exposure(asset)
    with django_assert_max_num_queries(12):
        response = dashboard_client.get("/assets/")
    assert response.context["assets"][0].open_exposures == 1


def test_asset_label_is_escaped(dashboard_client, org):
    asset = factories.make_asset(org, kind=Asset.Kind.CERTIFICATE, key="ab" * 32, label=XSS)
    factories.make_source(asset, source_kind="ct_feed", source_name=XSS)
    factories.make_exposure(asset, rule=Exposure.Rule.CERT_EXPIRING, title=XSS)
    factories.make_change(asset, kind="updated", field="label", old_value="old", new_value=XSS)
    for url in ("/assets/", f"/assets/{asset.pk}/", "/exposures/"):
        content = dashboard_client.get(url).content.decode()
        assert XSS not in content, url
        assert "&lt;script&gt;" in content, url


def test_detail_shows_provenance_links_services_and_history(dashboard_client, org):
    host = factories.make_asset(org, key="api.harborview-bank.example.test")
    ip = factories.make_asset(org, kind=Asset.Kind.IP, key="198.51.100.7")
    factories.make_link(host, ip)
    factories.make_service(ip, port=8443, service="https-alt")
    factories.make_source(host, source_name="old zone", last_seen_at=factories.TODAY.replace(month=9))
    factories.make_source(host, source_kind="nimbus", source_name="nimbus account 4471-2210-0093")
    factories.make_change(host, kind="owner_changed", field="owner_team", old_value="", new_value="payments")
    response = dashboard_client.get(f"/assets/{host.pk}/")
    assert [s.source_name for s in response.context["sources"]][0] == "nimbus account 4471-2210-0093"
    assert list(response.context["links_out"])[0].target == ip
    assert b"payments" in response.content
    assert b"8443/tcp" in dashboard_client.get(f"/assets/{ip.pk}/").content


def test_csv_streams_the_filtered_list(dashboard_client, org, other_org):
    factories.make_asset(org, kind=Asset.Kind.HOST, key="www.harborview-bank.example.test")
    ip = factories.make_asset(org, kind=Asset.Kind.IP, key="203.0.113.5", label='=HYPERLINK("http://x")')
    factories.make_exposure(ip)
    factories.make_asset(other_org, kind=Asset.Kind.IP, key="203.0.113.6")
    response = dashboard_client.get("/assets.csv?kind=ip")
    assert response.streaming
    assert response["Content-Type"] == "text/csv"
    assert 'filename="harborview-bank-assets-2026-11-05.csv"' in response["Content-Disposition"]
    header, *rows = _csv(response)
    assert header[:4] == ["id", "kind", "key", "label"]
    assert [(r[2], r[3], r[6]) for r in rows] == [("203.0.113.5", '\'=HYPERLINK("http://x")', "1")]


def test_csv_rejects_invalid_filter(dashboard_client, org):
    assert dashboard_client.get("/assets.csv?kind=printer").status_code == 400


def test_saved_view_round_trip(dashboard_client, org, dashboard_user):
    form = {"name": "Public IPs", "querystring": "q=203.&kind=ip&page=3"}
    response = dashboard_client.post("/views/", form)
    view = SavedView.objects.get(org=org, owner=dashboard_user)
    assert view.querystring == "kind=ip&q=203."
    assert response["Location"] == "/assets/?kind=ip&q=203."
    page = dashboard_client.get(response["Location"])
    assert b'href="/assets/?kind=ip&amp;q=203."' in page.content
    assert page.context["querystring"] == view.querystring

    duplicate = dashboard_client.post("/views/", {"name": "Public IPs", "querystring": ""}, follow=True)
    assert b"already have a view" in duplicate.content
    assert SavedView.objects.count() == 1


def test_saved_views_only_delete_own(dashboard_client, org, other_org, dashboard_user):
    shared = factories.make_saved_view(org, name="Shared")
    foreign = factories.make_saved_view(other_org, name="Theirs", owner=dashboard_user)
    own = factories.make_saved_view(org, name="Mine", owner=dashboard_user)
    assert dashboard_client.post("/views/", {"delete": shared.pk}).status_code == 404
    assert dashboard_client.post("/views/", {"delete": foreign.pk}).status_code == 404
    assert dashboard_client.post("/views/", {"delete": own.pk}).status_code == 302
    assert set(SavedView.objects.values_list("name", flat=True)) == {"Shared", "Theirs"}
    assert dashboard_client.get("/views/").status_code == 405


def test_ownership_page_lists_rules_in_precedence_order(dashboard_client, org, other_org):
    factories.make_rule(org, "*.harborview-bank.example.test", "platform", priority=200)
    factories.make_rule(org, "*.payments.harborview-bank.example.test", "payments", priority=10)
    factories.make_rule(other_org, "*", "theirs")
    factories.make_asset(org)
    response = dashboard_client.get("/ownership/")
    assert [r.team for r in response.context["rules"]] == ["payments", "platform"]
    assert response.context["unowned"] == 1


def test_exposure_overview_counts_open_by_severity(dashboard_client, org, other_org):
    asset = factories.make_asset(org, kind=Asset.Kind.IP)
    factories.make_exposure(asset, severity="high", subject="8443/tcp")
    factories.make_exposure(asset, severity="high", subject="22/tcp")
    factories.make_exposure(asset, severity="medium", subject="80/tcp", status="resolved")
    factories.make_exposure(factories.make_asset(other_org), severity="critical")
    response = dashboard_client.get("/exposures/")
    assert response.context["total"] == 2
    bars = {bar.label: bar.value for bar in response.context["chart"].bars}
    assert bars == {"critical": 0, "high": 2, "medium": 0, "low": 0}
    assert response.content.count(b'class="sev-bar') == 4


def test_bar_chart_scales_to_the_largest_value():
    chart = bar_chart({"high": 4, "low": 1}, SEVERITY_ORDER, width=480, label_width=80)
    widths = {bar.label: bar.width for bar in chart.bars}
    assert widths == {"critical": 0, "high": 360, "medium": 0, "low": 90}
    assert bar_chart({}, SEVERITY_ORDER).bars[0].width == 0
