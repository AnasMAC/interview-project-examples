"""Which org a dashboard request works on.

The API takes the org from the API key; the dashboard takes it from the
logged-in user's memberships. Never from a form field or a model id.
"""

from django.http import Http404

from atlas.core.models import Org

SESSION_KEY = "atlas_org"


def user_orgs(request) -> list[Org]:
    """Orgs the user is a member of, oldest first (cached on the request)."""
    if not hasattr(request, "_atlas_orgs"):
        request._atlas_orgs = list(Org.objects.filter(memberships__user=request.user).order_by("id"))
    return request._atlas_orgs


def current_org(request) -> Org:
    """The org picked with ``?org=<slug>`` (remembered in the session), else the user's first.

    404 when the user is not a member of the requested org, or of any org.
    """
    orgs = {org.slug: org for org in user_orgs(request)}
    requested = request.GET.get("org")
    if requested:
        if requested not in orgs:
            raise Http404("No such organisation.")
        request.session[SESSION_KEY] = requested
        return orgs[requested]
    remembered = request.session.get(SESSION_KEY)
    if remembered in orgs:
        return orgs[remembered]
    if not orgs:
        raise Http404("You are not a member of any organisation.")
    return next(iter(orgs.values()))


def org_context(request, org: Org) -> dict:
    """Template context every page needs for the header and the org switcher."""
    return {"org": org, "orgs": user_orgs(request)}
