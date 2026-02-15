"""Special Callsign Media Sharing - Streamlit Web Application.

Integrates with Quendaward (award_planner) to read special callsign
information and allows admins to upload/manage media for each callsign.
"""

import os
import hashlib
import hmac
import base64

import streamlit as st

import database as db
import media_utils as mu

# --- Configuration ---
ADMIN_PASSWORD_HASH = os.environ.get(
    "ADMIN_PASSWORD_HASH",
    # Default password: "admin" (sha256). Change via environment variable.
    hashlib.sha256(b"admin").hexdigest(),
)
APP_TITLE = os.environ.get("APP_TITLE", "Special Callsign Media Sharing")


def init():
    """One-time initialization."""
    db.init_db()


def check_password(password: str) -> bool:
    """Verify admin password."""
    candidate = hashlib.sha256(password.encode()).hexdigest()
    return hmac.compare_digest(candidate, ADMIN_PASSWORD_HASH)


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

    found_any = False
    for cs in display_callsigns:
        media_items = db.get_media_by_callsign(cs["id"], media_type=selected_type)
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

        # Group by media type
        type_groups: dict[str, list] = {}
        for item in media_items:
            type_groups.setdefault(item["media_type"], []).append(item)

        for mtype, items in type_groups.items():
            icon = mu.MEDIA_TYPE_ICONS.get(mtype, "")
            st.subheader(f"{icon} {mtype.capitalize()}s")
            render_media_grid(items, mtype)

        st.divider()

    if not found_any:
        st.info("No media found matching the selected filters.")


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

    elif media_type == "document":
        for item in items:
            file_path = mu.get_media_path(item["filename"])
            size_str = mu.format_file_size(item["file_size"]) if item["file_size"] else ""
            st.markdown(f"**{item['title']}**  \n{item['description'] or ''}")
            if os.path.exists(file_path):
                with open(file_path, "rb") as f:
                    st.download_button(
                        label=f"Download {item['original_filename']} ({size_str})",
                        data=f,
                        file_name=item["original_filename"],
                        key=f"dl_{item['id']}",
                    )
            else:
                st.warning(f"File missing: {item['original_filename']}")


# ──────────────────────────────────────────────
# ADMIN PAGES
# ──────────────────────────────────────────────

def page_admin_login():
    """Admin login page."""
    st.title("Admin Login")
    st.markdown("Enter the admin password to manage media content.")

    password = st.text_input("Password", type="password")
    if st.button("Login"):
        if check_password(password):
            st.session_state["admin_authenticated"] = True
            st.rerun()
        else:
            st.error("Invalid password.")


def page_admin_panel():
    """Admin panel for managing media content."""
    st.title("Admin Panel")

    if st.sidebar.button("Logout"):
        st.session_state["admin_authenticated"] = False
        st.rerun()

    tab_upload, tab_manage = st.tabs(["Upload Media", "Manage Media"])

    with tab_upload:
        admin_upload_media()

    with tab_manage:
        admin_manage_media()


def admin_upload_media():
    """Upload new media content."""
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

    title = st.text_input("Title")
    description = st.text_area("Description", height=100)

    all_extensions = []
    for exts in mu.ALLOWED_EXTENSIONS.values():
        all_extensions.extend(exts)

    uploaded_files = st.file_uploader(
        "Choose files",
        accept_multiple_files=True,
        type=[ext.lstrip(".") for ext in all_extensions],
    )

    if st.button("Upload", type="primary") and uploaded_files:
        if not title.strip():
            st.error("Title is required.")
            return

        success_count = 0
        for uploaded_file in uploaded_files:
            media_type = mu.detect_media_type(uploaded_file.name)
            if not media_type:
                st.warning(f"Unsupported file type: {uploaded_file.name}")
                continue

            stored_name, file_size = mu.save_uploaded_file(uploaded_file)
            db.create_media(
                award_id=award_id,
                title=title.strip(),
                description=description.strip(),
                media_type=media_type,
                filename=stored_name,
                original_filename=uploaded_file.name,
                file_size=file_size,
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

    for item in media_items:
        icon = mu.MEDIA_TYPE_ICONS.get(item["media_type"], "")
        with st.expander(
            f"{icon} {item['title']} — {item['callsign_name']} ({item['media_type']})"
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
                if st.button("Save changes", key=f"save_{item['id']}"):
                    db.update_media(item["id"], new_title, new_desc)
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

    # Navigation
    st.sidebar.title(APP_TITLE)
    if st.session_state["admin_authenticated"]:
        page = st.sidebar.radio("Navigation", ["Gallery", "Admin Panel"])
    else:
        page = st.sidebar.radio("Navigation", ["Gallery", "Admin Login"])

    if page == "Gallery":
        page_gallery()
    elif page == "Admin Login":
        page_admin_login()
    elif page == "Admin Panel":
        page_admin_panel()


if __name__ == "__main__":
    main()
