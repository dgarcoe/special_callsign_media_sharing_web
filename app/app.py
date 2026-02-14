"""Special Callsign Media Sharing - Streamlit Web Application."""

import os
import hashlib
import hmac

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


# ──────────────────────────────────────────────
# PUBLIC PAGES
# ──────────────────────────────────────────────

def page_gallery():
    """Public gallery: browse all media by callsign."""
    st.title(APP_TITLE)
    st.markdown("Browse media content organized by special callsign.")

    callsigns = db.get_all_callsigns()
    if not callsigns:
        st.info("No content has been published yet. Check back later!")
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

    for cs in display_callsigns:
        media_items = db.get_media_by_callsign(cs["id"], media_type=selected_type)
        if not media_items:
            continue

        st.header(f"{cs['name']}")
        if cs["description"]:
            st.caption(cs["description"])

        # Group by media type for cleaner display
        type_groups: dict[str, list] = {}
        for item in media_items:
            type_groups.setdefault(item["media_type"], []).append(item)

        for mtype, items in type_groups.items():
            icon = mu.MEDIA_TYPE_ICONS.get(mtype, "")
            st.subheader(f"{icon} {mtype.capitalize()}s")
            render_media_grid(items, mtype)

        st.divider()

    if not any(
        db.get_media_by_callsign(cs["id"], media_type=selected_type)
        for cs in display_callsigns
    ):
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
    st.markdown("Enter the admin password to manage content.")

    password = st.text_input("Password", type="password")
    if st.button("Login"):
        if check_password(password):
            st.session_state["admin_authenticated"] = True
            st.rerun()
        else:
            st.error("Invalid password.")


def page_admin_panel():
    """Admin panel for managing callsigns and media."""
    st.title("Admin Panel")

    if st.sidebar.button("Logout"):
        st.session_state["admin_authenticated"] = False
        st.rerun()

    tab_upload, tab_manage_media, tab_callsigns = st.tabs(
        ["Upload Media", "Manage Media", "Manage Callsigns"]
    )

    with tab_upload:
        admin_upload_media()

    with tab_manage_media:
        admin_manage_media()

    with tab_callsigns:
        admin_manage_callsigns()


def admin_upload_media():
    """Upload new media content."""
    st.subheader("Upload New Media")

    callsigns = db.get_all_callsigns()
    if not callsigns:
        st.warning("You need to create at least one callsign before uploading media.")
        st.markdown("Go to the **Manage Callsigns** tab to create one.")
        return

    callsign_options = {c["name"]: c["id"] for c in callsigns}
    selected_name = st.selectbox("Callsign", list(callsign_options.keys()))
    callsign_id = callsign_options[selected_name]

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
                callsign_id=callsign_id,
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

    callsigns = db.get_all_callsigns()
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


def admin_manage_callsigns():
    """Manage callsigns."""
    st.subheader("Manage Callsigns")

    # Create new callsign
    with st.form("new_callsign"):
        st.markdown("**Add New Callsign**")
        new_name = st.text_input("Callsign")
        new_desc = st.text_area("Description", height=80)
        submitted = st.form_submit_button("Add Callsign", type="primary")
        if submitted and new_name.strip():
            try:
                db.create_callsign(new_name, new_desc)
                st.success(f"Callsign {new_name.upper().strip()} created.")
                st.rerun()
            except Exception as e:
                if "UNIQUE" in str(e):
                    st.error("This callsign already exists.")
                else:
                    st.error(f"Error: {e}")

    st.divider()

    # List existing callsigns
    callsigns = db.get_all_callsigns()
    if not callsigns:
        st.info("No callsigns yet.")
        return

    for cs in callsigns:
        media_count = db.get_media_count_by_callsign(cs["id"])
        with st.expander(f"{cs['name']} ({media_count} media items)"):
            edit_name = st.text_input(
                "Name", value=cs["name"], key=f"csname_{cs['id']}"
            )
            edit_desc = st.text_area(
                "Description",
                value=cs["description"] or "",
                key=f"csdesc_{cs['id']}",
            )
            col1, col2 = st.columns(2)
            with col1:
                if st.button("Save", key=f"cssave_{cs['id']}"):
                    try:
                        db.update_callsign(cs["id"], edit_name, edit_desc)
                        st.success("Updated.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error: {e}")
            with col2:
                if st.button(
                    "Delete callsign and all media",
                    key=f"csdel_{cs['id']}",
                    type="secondary",
                ):
                    # Delete all media files first
                    media_items = db.get_media_by_callsign(cs["id"])
                    for item in media_items:
                        mu.delete_media_file(item["filename"])
                    db.delete_callsign(cs["id"])
                    st.success(f"Callsign {cs['name']} and all media deleted.")
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
