from django.urls import reverse


def _display_value(value, default="Non défini"):
    if isinstance(value, str):
        value = value.strip()
    return value or default


def _reverse_or_none(name, pk):
    if not pk:
        return None
    try:
        return reverse(name, kwargs={"pk": pk})
    except Exception:
        return None


def _with_count(value, count, singular_label, plural_label=None):
    if count is None:
        return value
    plural_label = plural_label or f"{singular_label}s"
    label = singular_label if count == 1 else plural_label
    return f"{value} — {count} {label}"


def _group_value_with_member_count(group):
    if not group:
        return _display_value(None)
    member_count = getattr(group, "member_count", None)
    if member_count is None:
        try:
            member_count = group.users.count()
        except Exception:
            member_count = None
    base = _display_value(getattr(group, "name", None))
    return _with_count(base, member_count, "membre")


def _role_value_with_member_count(role):
    if not role:
        return _display_value(None)
    member_count = getattr(role, "member_count", None)
    if member_count is None:
        try:
            member_count = role.users.count()
        except Exception:
            member_count = None
    base = _display_value(getattr(role, "name", None))
    return _with_count(base, member_count, "utilisateur")


def _graph_node(node_id, title, value=None, **kwargs):
    spec = {"id": node_id, "title": title, "value": value}
    spec.update(kwargs)
    return spec


def build_dependency_graph(node_specs=None, link_specs=None):
    node_specs = node_specs or []
    link_specs = link_specs or []
    nodes = []
    for spec in node_specs:
        if not spec or "id" not in spec:
            continue
        include_if = spec.get("include_if", True)
        if callable(include_if):
            try:
                include_if = include_if()
            except Exception:
                include_if = False
        if not include_if:
            continue
        raw_value = spec.get("value")
        if callable(raw_value):
            try:
                raw_value = raw_value()
            except Exception:
                raw_value = None
        default = spec.get("default", "Non défini")
        node = {
            "id": spec["id"],
            "title": spec.get("title"),
            "value": _display_value(raw_value, default),
        }
        if "url" in spec:
            node["url"] = spec["url"]
        if "optional" in spec:
            node["optional"] = spec["optional"]
        if "layout" in spec:
            node["layout"] = spec["layout"]
        nodes.append(node)

    links = []
    for link in link_specs:
        if not link or "from" not in link or "to" not in link:
            continue
        links.append({
            "from": link["from"],
            "to": link["to"],
            "route": link.get("route", "horizontal"),
        })

    return {"nodes": nodes, "links": links}


def build_user_dependency_graph(user):
    role = getattr(user, "role", None)
    group = getattr(user, "business_group", None)
    business_direction = getattr(group, "business_direction", None) if group else None
    group_direction = getattr(group, "direction", None) if group else None
    role_direction = getattr(role, "technical_direction", None) if role else None
    responsible = getattr(group, "responsible", None) if group else None

    if group_direction:
        direction_label = group_direction.name
        direction_url = _reverse_or_none("users:technicaldirection_change", getattr(group_direction, "pk", None))
    elif role_direction:
        direction_label = role_direction.name
        direction_url = _reverse_or_none("users:technicaldirection_change", getattr(role_direction, "pk", None))
    elif role and getattr(role, "is_admin_role", False):
        direction_label = "Transverse"
        direction_url = None
    else:
        direction_label = None
        direction_url = None

    responsible_label = None
    if responsible:
        responsible_label = responsible.get_full_name() or responsible.username

    user_label = user.get_username()
    role_label = _display_value(role.name if role else None)

    nodes = [
        _graph_node(
            "user",
            "Utilisateur",
            value=f"{user_label} — {role_label}",
            url=_reverse_or_none("users:user_change", getattr(user, "pk", None)),
        ),
        _graph_node(
            "group",
            "Groupe",
            value=_group_value_with_member_count(group),
            url=_reverse_or_none("users:businessgroup_change", getattr(group, "pk", None)),
        ),
        _graph_node(
            "business_direction",
            "Direction métier (facultatif)",
            value=business_direction.name if business_direction else None,
            url=_reverse_or_none("users:businessdirection_change", getattr(business_direction, "pk", None)),
            optional=True,
        ),
        _graph_node(
            "technical_direction",
            "Direction technique",
            value=direction_label,
            url=direction_url,
        ),
        _graph_node(
            "responsible",
            "Responsable du groupe",
            value=responsible_label,
            url=_reverse_or_none("users:user_detail", getattr(responsible, "pk", None)),
        ),
    ]

    links = [
        {"from": "user", "to": "group", "route": "horizontal"},
        {"from": "group", "to": "technical_direction", "route": "horizontal"},
        {"from": "group", "to": "business_direction", "route": "up"},
        {"from": "group", "to": "responsible", "route": "down"},
    ]

    return build_dependency_graph(nodes, links)


def build_group_dependency_graph(group):
    direction = getattr(group, "direction", None)
    business_direction = getattr(group, "business_direction", None)
    responsible = getattr(group, "responsible", None)
    group_value = _group_value_with_member_count(group)

    responsible_label = None
    if responsible:
        responsible_label = responsible.get_full_name() or responsible.username

    nodes = [
        _graph_node(
            "group",
            "Groupe",
            value=group_value,
            url=_reverse_or_none("users:businessgroup_change", getattr(group, "pk", None)),
        ),
        _graph_node(
            "technical_direction",
            "Direction technique",
            value=direction.name if direction else None,
            url=_reverse_or_none("users:technicaldirection_change", getattr(direction, "pk", None)),
        ),
        _graph_node(
            "business_direction",
            "Direction métier (facultatif)",
            value=business_direction.name if business_direction else None,
            url=_reverse_or_none("users:businessdirection_change", getattr(business_direction, "pk", None)),
            optional=True,
        ),
        _graph_node(
            "responsible",
            "Responsable du groupe",
            value=responsible_label,
            url=_reverse_or_none("users:user_detail", getattr(responsible, "pk", None)),
        ),
    ]

    links = [
        {"from": "group", "to": "technical_direction", "route": "horizontal"},
        {"from": "group", "to": "business_direction", "route": "up"},
        {"from": "group", "to": "responsible", "route": "down"},
    ]

    return build_dependency_graph(nodes, links)
