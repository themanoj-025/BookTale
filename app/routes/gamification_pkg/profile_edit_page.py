"""Profile edit page route."""

from flask import session

from app.routes.social_shared import avatar_html, get_current_user, render_page, storage
from app.routes.helpers import h


def render_profile_edit_page() -> str:
    """Render the profile edit page."""
    uid = session["user_id"]
    users_data = storage.load_users()
    user = users_data.get(uid)
    if not user:
        return render_page(
            "Not Found",
            '<div class="empty-state empty-state-variant"><div class="empty-icon"><i class="bi bi-person-x-fill"></i></div><div class="empty-title">User not found</div><div class="empty-desc">The user you are looking for does not exist.</div></div>',
        )
    bio_val = h(user.bio) if user.bio else ""
    name_val = h(user.name)
    email_val = h(user.email) if user.email else ""
    phone_val = h(user.phone) if user.phone else ""
    website_val = h(user.website) if user.website else ""
    location_val = h(user.location) if user.location else ""
    pp_val = h(user.profile_picture) if user.profile_picture else ""
    avatar = avatar_html(user.name, 64)
    CONTENT = """<div class="animate-in">
    <div class="profile-banner"></div>
    <div class="row justify-content-center" style="margin-top:-40px;">
        <div class="col-lg-8">
            <div class="glass-card p-4">
                <div class="d-flex gap-3 mb-4 align-items-center">
                    <div id="avatarPreview">AVATAR_PLACEHOLDER</div>
                    <div>
                        <h4 class="fw-bold mb-0">Edit Profile</h4>
                        <p class="text-muted small mb-0">@USER_ID_PLACEHOLDER &middot; ROLE_PLACEHOLDER</p>
                    </div>
                    <div class="ms-auto">
                        <a href="/profile/USER_ID_PLACEHOLDER" class="btn btn-outline btn-sm"><i class="bi bi-arrow-left"></i> Back</a>
                    </div>
                </div>
                <hr style="border-color:var(--border);">
                <form id="profileEditForm" onsubmit="return saveProfile()">
                    <div class="row">
                        <div class="col-md-6 mb-3">
                            <label class="form-label">Display Name</label>
                            <input type="text" id="editName" class="form-control" value="NAME_PLACEHOLDER" required>
                        </div>
                        <div class="col-md-6 mb-3">
                            <label class="form-label">Email</label>
                            <input type="email" id="editEmail" class="form-control" value="EMAIL_PLACEHOLDER">
                        </div>
                    </div>
                    <div class="row">
                        <div class="col-md-6 mb-3">
                            <label class="form-label">Phone</label>
                            <input type="text" id="editPhone" class="form-control" value="PHONE_PLACEHOLDER">
                        </div>
                        <div class="col-md-6 mb-3">
                            <label class="form-label">Website</label>
                            <input type="url" id="editWebsite" class="form-control" value="WEBSITE_PLACEHOLDER" placeholder="https://example.com">
                        </div>
                    </div>
                    <div class="mb-3">
                        <label class="form-label">Location</label>
                        <input type="text" id="editLocation" class="form-control" value="LOCATION_PLACEHOLDER" placeholder="City, Country">
                    </div>
                    <div class="mb-3">
                        <label class="form-label">Bio</label>
                        <textarea id="editBio" class="form-control" rows="4" placeholder="Tell us about yourself...">BIO_PLACEHOLDER</textarea>
                        <small class="text-muted" id="bioCharCount">0 / 500</small>
                    </div>
                    <div class="mb-3">
                        <label class="form-label">Profile Picture</label>
                        <div class="input-group">
                            <input type="url" id="editProfilePic" class="form-control" value="PP_PLACEHOLDER" placeholder="https://example.com/avatar.jpg" oninput="previewAvatar(this.value)">
                            <button class="btn btn-outline" type="button" onclick="document.getElementById(\\'editProfilePic\\').value=\\'\\';previewAvatar(\\'\\')"><i class="bi bi-x-lg"></i></button>
                        </div>
                        <small class="text-muted">Enter a URL, or upload an image below</small>
                    </div>
                    <div class="mb-3 p-3" style="border:2px dashed var(--border);border-radius:12px;text-align:center;">
                        <label class="form-label d-block">Upload New Avatar</label>
                        <input type="file" id="avatarUploadInput" accept="image/jpeg,image/png,image/gif,image/webp" style="display:none;" onchange="uploadAvatar(this)">
                        <button class="btn btn-outline" type="button" onclick="document.getElementById(\\'avatarUploadInput\\').click()">
                            <i class="bi bi-cloud-upload"></i> Choose File
                        </button>
                        <div id="avatarUploadStatus" class="mt-2 small text-muted">Max 5MB, JPG/PNG/GIF/WEBP</div>
                    </div>
                    <div class="d-flex gap-2">
                        <button type="submit" class="btn btn-primary" id="saveProfileBtn"><i class="bi bi-check-lg"></i> Save Changes</button>
                        <a href="/profile/USER_ID_PLACEHOLDER" class="btn btn-outline">Cancel</a>
                    </div>
                </form>
            </div>
        </div>
    </div>
</div>"""
    CONTENT = CONTENT.replace("AVATAR_PLACEHOLDER", avatar).replace(
        "AVATAR2_PLACEHOLDER", avatar
    )
    CONTENT = CONTENT.replace("USER_ID_PLACEHOLDER", h(uid))
    CONTENT = CONTENT.replace("ROLE_PLACEHOLDER", h(user.role.upper()))
    CONTENT = CONTENT.replace("NAME_PLACEHOLDER", name_val)
    CONTENT = CONTENT.replace("EMAIL_PLACEHOLDER", email_val)
    CONTENT = CONTENT.replace("PHONE_PLACEHOLDER", phone_val)
    CONTENT = CONTENT.replace("WEBSITE_PLACEHOLDER", website_val)
    CONTENT = CONTENT.replace("LOCATION_PLACEHOLDER", location_val)
    CONTENT = CONTENT.replace("BIO_PLACEHOLDER", bio_val)
    CONTENT = CONTENT.replace("PP_PLACEHOLDER", pp_val)
    CONTENT += """
<script>
function saveProfile() {
    var btn = document.getElementById("saveProfileBtn");
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner-border spinner-border-sm"></span> Saving...';
    var data = {
        name: document.getElementById("editName").value.trim(),
        email: document.getElementById("editEmail").value.trim(),
        phone: document.getElementById("editPhone").value.trim(),
        website: document.getElementById("editWebsite").value.trim(),
        location: document.getElementById("editLocation").value.trim(),
        bio: document.getElementById("editBio").value.trim(),
        profile_picture: document.getElementById("editProfilePic").value.trim()
    };
    if (!data.name) { showToast("Name is required", "error"); btn.disabled = false; btn.innerHTML = '<i class="bi bi-check-lg"></i> Save Changes'; return false; }
    fetch("/api/profile/update", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify(data)
    }).then(function(r){ return r.json() }).then(function(d){
        if (d.success) {
            showToast("Profile updated!", "success");
            setTimeout(function(){ window.location.href = '/profile/""" + h(uid) + """'; }, 1000);
        } else {
            showToast(d.error || "Failed to update", "error");
            btn.disabled = false;
            btn.innerHTML = '<i class="bi bi-check-lg"></i> Save Changes';
        }
    }).catch(function(){
        showToast("Network error", "error");
        btn.disabled = false;
        btn.innerHTML = '<i class="bi bi-check-lg"></i> Save Changes';
    });
    return false;
}
function previewAvatar(url) {
    var preview = document.getElementById("avatarPreview");
    if (url) {
        preview.innerHTML = '<div class="avatar" style="width:64px;height:64px;background-size:cover;background-image:url(' + encodeURI(url) + ');border-radius:50%;border:3px solid var(--bg);box-shadow:0 4px 12px rgba(0,0,0,.1);"></div>';
    } else {
        preview.innerHTML = "AVATAR2_PLACEHOLDER";
    }
}
function uploadAvatar(input) {
    var file = input.files[0];
    if (!file) return;
    var status = document.getElementById("avatarUploadStatus");
    var btn = input.parentElement.querySelector("button");
    var oldHtml = btn.innerHTML;
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner-border spinner-border-sm"></span> Uploading...';
    status.textContent = "Uploading...";
    var formData = new FormData();
    formData.append("file", file);
    formData.append("type", "avatar");
    fetch("/api/upload", {
        method: "POST",
        body: formData
    }).then(function(r){ return r.json() }).then(function(d){
        if (d.success) {
            document.getElementById("editProfilePic").value = d.url;
            previewAvatar(d.url);
            status.innerHTML = '<span class="text-success"><i class="bi bi-check-circle"></i> Uploaded!</span> ' + d.url;
            showToast("Avatar uploaded!", "success");
        } else {
            status.textContent = d.error || "Upload failed";
            showToast(d.error || "Upload failed", "error");
        }
        btn.disabled = false;
        btn.innerHTML = oldHtml;
    }).catch(function(){
        status.textContent = "Network error";
        showToast("Network error", "error");
        btn.disabled = false;
        btn.innerHTML = oldHtml;
    });
    input.value = "";
}
document.addEventListener("DOMContentLoaded", function(){
    var bio = document.getElementById("editBio");
    var cc = document.getElementById("bioCharCount");
    if (bio && cc) {
        cc.textContent = bio.value.length + " / 500";
        bio.addEventListener("input", function(){
            var len = bio.value.length;
            cc.textContent = len + " / 500";
            if (len > 500) { bio.value = bio.value.substring(0,500); cc.textContent = "500 / 500"; }
        });
    }
});
</script>"""
    return render_page("Edit Profile", CONTENT)
