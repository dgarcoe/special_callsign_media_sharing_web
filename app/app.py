"""Special Callsign Media Sharing - Streamlit Web Application.

Integrates with Quendaward (award_planner) to read special callsign
information and allows admins to upload/manage media for each callsign.
"""

import os
import base64

import streamlit as st

import database as db
import media_utils as mu

# --- Configuration ---
APP_TITLE = os.environ.get("APP_TITLE", "Special Callsign Media Sharing")


def init():
    """One-time initialization."""
    db.init_db()


def render_award_badge(award: dict):
    """Render award image and metadata in the sidebar or inline."""
    if award.get("image_data"):
        img_b64 = base64.b64encode(award["image_data"]).decode()
        mime = award.get("image_type", "image/png")
        st.image(f"data:{mime};base64,{img_b64}", width=150)
    if award.get("start_date") or award.get("end_date"):
        dates = f"{award.get('start_date', '?')} - {award.get('end_date', '?')}"
        st.caption(f"Active: {dates}")
    if award.get("qrz_link"):
        st.markdown(f"[QRZ Page]({award['qrz_link']})")


# ──────────────────────────────────────────────
# PUBLIC PAGES
# ──────────────────────────────────────────────

def page_gallery():
    """Public gallery: browse all media by special callsign."""
    st.title(APP_TITLE)
    st.markdown("Browse media content organized by special callsign.")

    callsigns = db.get_all_callsigns()
    if not callsigns:
        st.info("No special callsigns have been configured in Quendaward yet.")
        return

    # Sidebar filters
    st.sidebar.header("Filters")
    type_filter = st.sidebar.selectbox(
        "Media type",
        ["All", "Image", "Video", "Audio", "Document"],
    )
    selected_type = None if type_filter == "All" else type_filter.lower()

    callsign_names = ["All callsigns"] + [c["name"] for c in callsigns]
    selected_callsign = st.sidebar.selectbox("Callsign", callsign_names)

    # Determine which callsigns to show
    if selected_callsign == "All callsigns":
        display_callsigns = callsigns
    else:
        display_callsigns = [c for c in callsigns if c["name"] == selected_callsign]

    # Group filter -- collect groups across displayed callsigns
    all_groups_for_filter: list[dict] = []
    for cs in display_callsigns:
        all_groups_for_filter.extend(db.get_groups_by_callsign(cs["id"]))
    group_filter_names = ["All groups"] + [g["name"] for g in all_groups_for_filter]
    selected_group_filter = st.sidebar.selectbox("Group", group_filter_names)

    # Resolve selected group ID (None = show all)
    if selected_group_filter == "All groups":
        filter_group_id = None
    else:
        match = next((g for g in all_groups_for_filter if g["name"] == selected_group_filter), None)
        filter_group_id = match["id"] if match else None

    found_any = False
    for cs in display_callsigns:
        media_items = db.get_media_by_callsign(cs["id"], media_type=selected_type)
        # Apply group filter
        if filter_group_id is not None:
            media_items = [i for i in media_items if i.get("group_id") == filter_group_id]
        if not media_items:
            continue

        found_any = True
        col_header, col_badge = st.columns([3, 1])
        with col_header:
            st.header(cs["name"])
            if cs.get("description"):
                st.markdown(cs["description"])
        with col_badge:
            render_award_badge(cs)

        # Organise items by group, then by media type within each group
        groups = db.get_groups_by_callsign(cs["id"])
        group_map: dict[int | None, list[dict]] = {}
        for item in media_items:
            group_map.setdefault(item.get("group_id"), []).append(item)

        # Render grouped items first (in group sort order), then ungrouped
        rendered_groups = [(g["id"], g["name"]) for g in groups if g["id"] in group_map]
        if None in group_map:
            rendered_groups.append((None, "Other"))

        for gid, gname in rendered_groups:
            items_in_group = group_map[gid]
            if gid is not None:
                st.subheader(gname)

            # Sub-group by media type within this group
            type_groups: dict[str, list] = {}
            for item in items_in_group:
                type_groups.setdefault(item["media_type"], []).append(item)

            for mtype, items in type_groups.items():
                icon = mu.MEDIA_TYPE_ICONS.get(mtype, "")
                label = f"{icon} {mtype.capitalize()}s"
                if gid is None and len(rendered_groups) > 1:
                    st.subheader(label)
                else:
                    st.markdown(f"**{label}**")
                render_media_grid(items, mtype)

        # Download all media for this callsign as ZIP
        zip_data = mu.build_zip(media_items)
        if zip_data:
            st.download_button(
                label=f"Download all {cs['name']} media as ZIP",
                data=zip_data,
                file_name=f"{cs['name']}_media.zip",
                mime="application/zip",
                key=f"zip_{cs['id']}",
            )

        st.divider()

    if not found_any:
        st.info("No media found matching the selected filters.")


def _render_download_button(item: dict):
    """Render a download button for a single media item."""
    file_path = mu.get_media_path(item["filename"])
    if os.path.exists(file_path):
        size_str = mu.format_file_size(item["file_size"]) if item["file_size"] else ""
        label = f"Download ({size_str})" if size_str else "Download"
        with open(file_path, "rb") as f:
            st.download_button(
                label=label,
                data=f,
                file_name=item["original_filename"],
                key=f"dl_{item['id']}",
            )


def render_media_grid(items: list[dict], media_type: str):
    """Render a grid of media items."""
    if media_type == "image":
        cols = st.columns(3)
        for idx, item in enumerate(items):
            with cols[idx % 3]:
                file_path = mu.get_media_path(item["filename"])
                if os.path.exists(file_path):
                    st.image(file_path, caption=item["title"], use_container_width=True)
                else:
                    st.warning(f"File missing: {item['original_filename']}")
                if item["description"]:
                    st.caption(item["description"])
                _render_download_button(item)

    elif media_type == "video":
        for item in items:
            file_path = mu.get_media_path(item["filename"])
            st.markdown(f"**{item['title']}**")
            if item["description"]:
                st.caption(item["description"])
            if os.path.exists(file_path):
                st.video(file_path)
            else:
                st.warning(f"File missing: {item['original_filename']}")
            _render_download_button(item)

    elif media_type == "audio":
        for item in items:
            file_path = mu.get_media_path(item["filename"])
            st.markdown(f"**{item['title']}**")
            if item["description"]:
                st.caption(item["description"])
            if os.path.exists(file_path):
                st.audio(file_path)
            else:
                st.warning(f"File missing: {item['original_filename']}")
            _render_download_button(item)

    elif media_type == "document":
        for item in items:
            file_path = mu.get_media_path(item["filename"])
            st.markdown(f"**{item['title']}**  \n{item['description'] or ''}")
            if not os.path.exists(file_path):
                st.warning(f"File missing: {item['original_filename']}")
            _render_download_button(item)


# ──────────────────────────────────────────────
# ADMIN PAGES
# ──────────────────────────────────────────────

def admin_manage_groups():
    """Create, rename, reorder, and delete media groups per callsign."""
    from streamlit_sortables import sort_items
    import re

    st.subheader("Manage Groups")

    callsigns = db.get_all_callsigns()
    if not callsigns:
        st.info("No callsigns configured in Quendaward.")
        return

    callsign_options = {c["name"]: c["id"] for c in callsigns}
    selected_name = st.selectbox(
        "Select callsign", list(callsign_options.keys()), key="groups_callsign"
    )
    award_id = callsign_options[selected_name]

    # --- Create new group ---
    ALL_MEDIA_TYPES = ["image", "video", "audio", "document"]
    all_media = db.get_media_by_callsign(award_id)

    st.markdown("---")
    new_group_name = st.text_input("New group name", key="new_group_name")
    new_allowed = st.multiselect(
        "Allowed content types",
        ALL_MEDIA_TYPES,
        default=ALL_MEDIA_TYPES,
        format_func=lambda t: f"{mu.MEDIA_TYPE_ICONS.get(t, '')} {t.capitalize()}",
        key="new_group_types",
    )

    # Pick existing media to include in the new group
    eligible_new = [
        m for m in all_media
        if m["media_type"] in (new_allowed or ALL_MEDIA_TYPES)
    ]
    if eligible_new:
        pick_labels = {
            f"{mu.MEDIA_TYPE_ICONS.get(m['media_type'], '')} {m['title']} ({m['media_type']})": m["id"]
            for m in eligible_new
        }
        selected_items = st.multiselect(
            "Include existing media in this group",
            list(pick_labels.keys()),
            key="new_group_items",
        )
    else:
        selected_items = []

    if st.button("Create group", key="btn_create_group"):
        if new_group_name.strip():
            types_arg = new_allowed if len(new_allowed) < len(ALL_MEDIA_TYPES) else None
            gid = db.create_group(award_id, new_group_name, allowed_types=types_arg)
            if selected_items:
                db.assign_media_to_group(gid, [pick_labels[l] for l in selected_items])
            st.success(f"Group '{new_group_name.strip()}' created.")
            st.rerun()
        else:
            st.error("Group name cannot be empty.")

    # --- List existing groups ---
    groups = db.get_groups_by_callsign(award_id)
    if not groups:
        st.info("No groups yet. Create one above.")
        return

    st.markdown("---")

    # Drag-and-drop group ordering
    labels = [f"[{g['id']}] {g['name']}" for g in groups]
    st.markdown("Drag groups to reorder, then click **Save group order**.")
    new_labels = sort_items(labels, direction="vertical", key=f"gsort_{award_id}")

    if st.button("Save group order", key="btn_save_group_order", type="primary"):
        new_ids = []
        for label in new_labels:
            m = re.search(r"\[(\d+)\]", label)
            if m:
                new_ids.append(int(m.group(1)))
        db.update_group_order(new_ids)
        st.success("Group order saved.")
        st.rerun()

    # Edit / delete individual groups
    st.markdown("---")
    for g in groups:
        current_types = g["allowed_types"].split(",") if g.get("allowed_types") else ALL_MEDIA_TYPES
        current_items = [m for m in all_media if m.get("group_id") == g["id"]]
        item_count = len(current_items)
        types_label = ", ".join(t.capitalize() for t in current_types)
        with st.expander(f"{g['name']}  --  {types_label}  ({item_count} items)"):
            renamed = st.text_input("Name", value=g["name"], key=f"grp_name_{g['id']}")
            edited_types = st.multiselect(
                "Allowed content types",
                ALL_MEDIA_TYPES,
                default=current_types,
                format_func=lambda t: f"{mu.MEDIA_TYPE_ICONS.get(t, '')} {t.capitalize()}",
                key=f"grp_types_{g['id']}",
            )

            # Media item membership
            eligible = [
                m for m in all_media
                if m["media_type"] in (edited_types or ALL_MEDIA_TYPES)
            ]
            item_labels = {
                f"{mu.MEDIA_TYPE_ICONS.get(m['media_type'], '')} {m['title']} ({m['media_type']})": m["id"]
                for m in eligible
            }
            current_labels = [
                l for l, mid in item_labels.items()
                if any(ci["id"] == mid for ci in current_items)
            ]
            selected_labels = st.multiselect(
                "Media in this group",
                list(item_labels.keys()),
                default=current_labels,
                key=f"grp_items_{g['id']}",
            )

            col_save, col_del = st.columns(2)
            with col_save:
                if st.button("Save", key=f"grp_save_{g['id']}"):
                    if renamed.strip():
                        types_arg = edited_types if len(edited_types) < len(ALL_MEDIA_TYPES) else None
                        db.update_group(g["id"], renamed, allowed_types=types_arg)
                        # Compute membership changes
                        new_ids = {item_labels[l] for l in selected_labels}
                        old_ids = {m["id"] for m in current_items}
                        to_add = new_ids - old_ids
                        to_remove = old_ids - new_ids
                        if to_add:
                            db.assign_media_to_group(g["id"], list(to_add))
                        if to_remove:
                            db.assign_media_to_group(None, list(to_remove))
                        st.success("Group updated.")
                        st.rerun()
            with col_del:
                if st.button("Delete", key=f"grp_del_{g['id']}"):
                    db.delete_group(g["id"])
                    st.success("Group deleted. Its media items are now ungrouped.")
                    st.rerun()


def admin_reorder_media():
    """Drag-and-drop reordering of media items per callsign and group."""
    from streamlit_sortables import sort_items
    import re

    st.subheader("Reorder Media")

    callsigns = db.get_all_callsigns()
    if not callsigns:
        st.info("No callsigns configured in Quendaward.")
        return

    callsign_options = {c["name"]: c["id"] for c in callsigns}
    selected_name = st.selectbox(
        "Select callsign", list(callsign_options.keys()), key="reorder_callsign"
    )
    award_id = callsign_options[selected_name]

    media_items = db.get_media_by_callsign(award_id)
    if not media_items:
        st.info("No media uploaded for this callsign yet.")
        return

    # Let admin choose which group to reorder (or all items)
    groups = db.get_groups_by_callsign(award_id)
    scope_options = {"All items": None}
    for g in groups:
        scope_options[g["name"]] = g["id"]
    has_ungrouped = any(item.get("group_id") is None for item in media_items)
    if has_ungrouped and groups:
        scope_options["(Ungrouped)"] = "ungrouped"

    scope_name = st.selectbox("Group", list(scope_options.keys()), key="reorder_scope")
    scope_val = scope_options[scope_name]

    # Filter items by scope
    if scope_val is None:
        filtered = media_items
    elif scope_val == "ungrouped":
        filtered = [i for i in media_items if i.get("group_id") is None]
    else:
        filtered = [i for i in media_items if i.get("group_id") == scope_val]

    if not filtered:
        st.info("No items in this group.")
        return

    labels = [
        f"{mu.MEDIA_TYPE_ICONS.get(item['media_type'], '')} [{item['id']}] {item['title']}"
        for item in filtered
    ]

    st.markdown("Drag items into the desired order, then click **Save order**.")
    new_labels = sort_items(labels, direction="vertical", key=f"sort_{award_id}_{scope_val}")

    if st.button("Save order", key="btn_save_order", type="primary"):
        new_ids = []
        for label in new_labels:
            m = re.search(r"\[(\d+)\]", label)
            if m:
                new_ids.append(int(m.group(1)))
        db.update_media_order(new_ids)
        st.success("Order saved.")


def page_admin_login():
    """Admin login page using Quendaward operator credentials."""
    st.title("Admin Login")
    st.markdown("Log in with your Quendaward admin callsign and password.")

    callsign = st.text_input("Callsign")
    password = st.text_input("Password", type="password")
    if st.button("Login"):
        if not callsign.strip() or not password:
            st.error("Both callsign and password are required.")
        else:
            operator = db.authenticate_admin(callsign, password)
            if operator:
                st.session_state["admin_authenticated"] = True
                st.session_state["admin_callsign"] = operator["callsign"]
                st.session_state["admin_name"] = operator["operator_name"]
                st.session_state["page"] = "Admin Panel"
                st.rerun()
            else:
                st.error("Invalid credentials or insufficient permissions.")


def page_admin_panel():
    """Admin panel for managing media content."""
    st.title("Admin Panel")

    admin_cs = st.session_state.get("admin_callsign", "")
    admin_name = st.session_state.get("admin_name", "")
    if admin_cs:
        label = f"{admin_name} ({admin_cs})" if admin_name else admin_cs
        st.sidebar.markdown(f"Logged in as **{label}**")

    if st.sidebar.button("Logout"):
        st.session_state["admin_authenticated"] = False
        st.session_state.pop("admin_callsign", None)
        st.session_state.pop("admin_name", None)
        st.session_state["page"] = "Gallery"
        st.rerun()

    tab_upload, tab_manage, tab_groups, tab_reorder = st.tabs(
        ["Upload Media", "Manage Media", "Groups", "Reorder"]
    )

    with tab_upload:
        admin_upload_media()

    with tab_manage:
        admin_manage_media()

    with tab_groups:
        admin_manage_groups()

    with tab_reorder:
        admin_reorder_media()


def admin_upload_media():
    """Upload new media content with per-file title and description."""
    st.subheader("Upload New Media")

    callsigns = db.get_all_callsigns()
    if not callsigns:
        st.warning(
            "No special callsigns found in Quendaward. "
            "Create awards in Quendaward first, then come back to upload media."
        )
        return

    callsign_options = {c["name"]: c["id"] for c in callsigns}
    selected_name = st.selectbox("Special Callsign", list(callsign_options.keys()))
    award_id = callsign_options[selected_name]

    # Show selected award info
    award = db.get_callsign(award_id)
    if award:
        render_award_badge(award)

    # Group selector (filtered to groups that allow the uploaded types)
    groups = db.get_groups_by_callsign(award_id)
    group_options = {"(No group)": None}
    for g in groups:
        group_options[g["name"]] = g["id"]
    selected_group_name = st.selectbox("Group / Folder", list(group_options.keys()))
    selected_group_id = group_options[selected_group_name]

    # Show which types the selected group accepts
    if selected_group_id is not None:
        sel_group = next((g for g in groups if g["id"] == selected_group_id), None)
        if sel_group and sel_group.get("allowed_types"):
            allowed = sel_group["allowed_types"].split(",")
            labels = ", ".join(f"{mu.MEDIA_TYPE_ICONS.get(t, '')} {t.capitalize()}" for t in allowed)
            st.caption(f"This group accepts: {labels}")

    all_extensions = []
    for exts in mu.ALLOWED_EXTENSIONS.values():
        all_extensions.extend(exts)

    uploaded_files = st.file_uploader(
        "Choose files",
        accept_multiple_files=True,
        type=[ext.lstrip(".") for ext in all_extensions],
    )

    if not uploaded_files:
        return

    # Per-file title and description fields
    st.markdown("---")
    st.markdown("**Fill in details for each file:**")

    file_metadata: list[dict] = []
    all_valid = True
    for idx, uploaded_file in enumerate(uploaded_files):
        media_type = mu.detect_media_type(uploaded_file.name)
        if not media_type:
            st.warning(f"Unsupported file type: {uploaded_file.name} (will be skipped)")
            continue

        icon = mu.MEDIA_TYPE_ICONS.get(media_type, "")
        with st.expander(f"{icon} {uploaded_file.name}", expanded=True):
            title = st.text_input(
                "Title", key=f"upload_title_{idx}",
                value=uploaded_file.name.rsplit(".", 1)[0],
            )
            description = st.text_area(
                "Description", key=f"upload_desc_{idx}", height=68,
            )
            if not title.strip():
                all_valid = False
            file_metadata.append({
                "file": uploaded_file,
                "title": title,
                "description": description,
                "media_type": media_type,
            })

    if not file_metadata:
        return

    if st.button("Upload all", type="primary"):
        if not all_valid:
            st.error("Every file needs a title.")
            return

        # Validate types against selected group
        if selected_group_id is not None:
            sel_group = next((g for g in groups if g["id"] == selected_group_id), None)
            if sel_group and sel_group.get("allowed_types"):
                allowed = set(sel_group["allowed_types"].split(","))
                rejected = [m["file"].name for m in file_metadata if m["media_type"] not in allowed]
                if rejected:
                    st.error(
                        f"The group '{sel_group['name']}' does not accept these file types: "
                        + ", ".join(rejected)
                    )
                    return

        success_count = 0
        for meta in file_metadata:
            stored_name, file_size = mu.save_uploaded_file(meta["file"])
            db.create_media(
                award_id=award_id,
                title=meta["title"].strip(),
                description=meta["description"].strip(),
                media_type=meta["media_type"],
                filename=stored_name,
                original_filename=meta["file"].name,
                file_size=file_size,
                group_id=selected_group_id,
            )
            success_count += 1

        if success_count:
            st.success(f"Uploaded {success_count} file(s) successfully.")
            st.rerun()


def admin_manage_media():
    """Manage existing media items."""
    st.subheader("Manage Media")

    type_filter = st.selectbox(
        "Filter by type",
        ["All", "Image", "Video", "Audio", "Document"],
        key="manage_type_filter",
    )
    selected_type = None if type_filter == "All" else type_filter.lower()

    media_items = db.get_all_media(media_type=selected_type)
    if not media_items:
        st.info("No media found.")
        return

    # Build a lookup of groups across all callsigns for the manage view
    all_callsign_ids = {item["award_id"] for item in media_items}
    groups_by_award: dict[int, list[dict]] = {}
    for aid in all_callsign_ids:
        groups_by_award[aid] = db.get_groups_by_callsign(aid)

    for item in media_items:
        icon = mu.MEDIA_TYPE_ICONS.get(item["media_type"], "")
        group_label = ""
        if item.get("group_id"):
            for g in groups_by_award.get(item["award_id"], []):
                if g["id"] == item["group_id"]:
                    group_label = f" [{g['name']}]"
                    break
        with st.expander(
            f"{icon} {item['title']} — {item['callsign_name']}{group_label} ({item['media_type']})"
        ):
            col1, col2 = st.columns([2, 1])
            with col1:
                new_title = st.text_input(
                    "Title", value=item["title"], key=f"title_{item['id']}"
                )
                new_desc = st.text_area(
                    "Description",
                    value=item["description"] or "",
                    key=f"desc_{item['id']}",
                )
                # Group reassignment (only show groups compatible with this item's type)
                item_groups = groups_by_award.get(item["award_id"], [])
                group_opts = {"(No group)": None}
                for g in item_groups:
                    if g.get("allowed_types"):
                        if item["media_type"] not in g["allowed_types"].split(","):
                            continue
                    group_opts[g["name"]] = g["id"]
                current_group_idx = 0
                for idx, (_, gid) in enumerate(group_opts.items()):
                    if gid == item.get("group_id"):
                        current_group_idx = idx
                        break
                new_group_name = st.selectbox(
                    "Group", list(group_opts.keys()),
                    index=current_group_idx, key=f"group_{item['id']}",
                )
                new_group_id = group_opts[new_group_name]

                if st.button("Save changes", key=f"save_{item['id']}"):
                    db.update_media(item["id"], new_title, new_desc, group_id=new_group_id)
                    st.success("Updated.")
                    st.rerun()
            with col2:
                st.markdown(f"**File:** {item['original_filename']}")
                st.markdown(f"**Type:** {item['media_type']}")
                if item["file_size"]:
                    st.markdown(f"**Size:** {mu.format_file_size(item['file_size'])}")
                st.markdown(f"**Uploaded:** {item['uploaded_at']}")

                # Preview
                file_path = mu.get_media_path(item["filename"])
                if os.path.exists(file_path):
                    if item["media_type"] == "image":
                        st.image(file_path, width=200)
                    elif item["media_type"] == "audio":
                        st.audio(file_path)

                if st.button("Delete", key=f"del_{item['id']}", type="secondary"):
                    filename = db.delete_media(item["id"])
                    if filename:
                        mu.delete_media_file(filename)
                    st.success("Deleted.")
                    st.rerun()


# ──────────────────────────────────────────────
# MAIN
# ──────────────────────────────────────────────

def main():
    st.set_page_config(
        page_title=APP_TITLE,
        page_icon="\U0001f4e1",
        layout="wide",
    )

    init()

    # Initialize session state
    if "admin_authenticated" not in st.session_state:
        st.session_state["admin_authenticated"] = False
    if "page" not in st.session_state:
        st.session_state["page"] = "Gallery"

    # Navigation
    st.sidebar.title(APP_TITLE)
    if st.session_state["admin_authenticated"]:
        options = ["Gallery", "Admin Panel"]
    else:
        options = ["Gallery", "Admin Login"]

    # Ensure stored page is valid for the current option set
    default = options.index(st.session_state["page"]) if st.session_state["page"] in options else 0

    page = st.sidebar.radio("Navigation", options, index=default, key="nav_radio")
    st.session_state["page"] = page

    if page == "Gallery":
        page_gallery()
    elif page == "Admin Login":
        page_admin_login()
    elif page == "Admin Panel":
        page_admin_panel()


if __name__ == "__main__":
    main()
