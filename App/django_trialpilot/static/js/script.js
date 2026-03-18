document.addEventListener("DOMContentLoaded", function () {
    const modal = new bootstrap.Modal(document.getElementById("diaryModal"));
    const modalBody = document.getElementById("diaryModalBody");
    const confirmBtn = document.getElementById("confirmDiaryAction");

    document.querySelectorAll(".diary-card-trigger").forEach(card => {
        card.addEventListener("click", function () {
            const diaryId = this.dataset.diaryId;
            const diaryTitle = this.dataset.diaryTitle;
            const extracted = this.dataset.diaryExtracted === "True";

            if (extracted) {
                modalBody.innerHTML = `
                    <p>The diary <strong>${diaryTitle}</strong> has already been processed.</p>
                    <p>It cannot be processed again.</p>
                `;

                // Hide the Continue button
                confirmBtn.style.display = "none";

            } else {
                modalBody.innerHTML = `
                    <p>The diary <strong>${diaryTitle}</strong> has not been processed yet.</p>
                    <p>It will now be sent to the parameter extraction pipeline.</p>
                `;

                // Show the Continue button
                confirmBtn.style.display = "inline-block";
                confirmBtn.href = `/diaries/${diaryId}/extract`;
            }

            modal.show();
        });
    });
});

document.addEventListener("DOMContentLoaded", function () {

    const form = document.getElementById("uploadForm");
    const dropZone = document.getElementById("dropZone");
    const fileInput = document.getElementById("fileInput");
    const preview = document.getElementById("filePreview");

    const progressContainer = document.getElementById("progressContainer");
    const progressBar = document.getElementById("progressBar");
    const progressText = document.getElementById("progressText");

    const uploadModal = document.getElementById("uploadModal");

    if (!dropZone) return;

    dropZone.addEventListener("click", () => fileInput.click());

    dropZone.addEventListener("dragover", (e) => {
        e.preventDefault();
        dropZone.classList.add("bg-light");
    });

    dropZone.addEventListener("dragleave", () => {
        dropZone.classList.remove("bg-light");
    });

    dropZone.addEventListener("drop", (e) => {
        e.preventDefault();

        const files = e.dataTransfer.files;
        fileInput.files = files;

        showPreview(files[0]);
    });

    uploadModal.addEventListener("hidden.bs.modal", () => {
        fileInput.value = "";

        preview.innerHTML = "";

        const errorBox = document.getElementById("uploadError");
        errorBox.classList.add("d-none");
        errorBox.innerText = "";

        progressContainer.style.display = "none";
        progressBar.style.width = "0%";
        progressText.innerText = "Uploading... 0%";

        dropZone.classList.remove("bg-light");
    });

    fileInput.addEventListener("change", () => {
        showPreview(fileInput.files[0]);
    });

    function showPreview(file) {
        const allowed = ["pdf", "txt"];
        const ext = file.name.split('.').pop().toLowerCase();

        const errorBox = document.getElementById("uploadError");

        if (!allowed.includes(ext)) {
            errorBox.classList.remove("d-none");
            errorBox.innerText = "Only PDF and TXT files are allowed.";

            preview.innerHTML = "";
            progressContainer.style.display = "none";
            fileInput.value = "";

            return;
        }

        errorBox.classList.add("d-none");
        errorBox.innerText = "";

        let icon = "bi-file-earmark-text";
        if (ext === "pdf") icon = "bi-filetype-pdf";
        if (ext === "txt") icon = "bi-filetype-txt";

        preview.innerHTML = `
        <div class="d-flex align-items-center gap-2">
            <i class="bi ${icon}" style="font-size:1.5rem;"></i>
            <span>${file.name}</span>
        </div>
    `;

        progressContainer.style.display = "block";
        progressBar.style.width = "0%";
        progressText.innerText = "Ready to upload";
    }

    form.addEventListener("submit", function (e) {

        e.preventDefault();

        if (!fileInput.files.length) {
            alert("Please select a valid PDF or TXT file.");
            return;
        }

        const formData = new FormData(form);

        const xhr = new XMLHttpRequest();
        xhr.open("POST", form.action, true);

        // CSRF
        xhr.setRequestHeader("X-CSRFToken", getCookie("csrftoken"));


        xhr.upload.addEventListener("progress", function (e) {
            if (e.lengthComputable) {
                const percent = Math.round((e.loaded / e.total) * 100);

                progressBar.style.width = percent + "%";
                progressText.innerText = `Uploading... ${percent}%`;

                progressBar.classList.add("progress-bar-animated");
            }
        });

        xhr.onload = function () {
            if (xhr.status === 200) {
                progressBar.style.width = "100%";
                progressBar.classList.remove("progress-bar-animated");
                progressText.innerText = "Upload complete ✅";

                setTimeout(() => location.reload(), 1000);
            } else {
                progressText.innerText = "Upload failed ❌";
            }
        };

        xhr.send(formData);
    });

    // CSRF helper (Django)
    function getCookie(name) {
        let cookieValue = null;
        if (document.cookie && document.cookie !== "") {
            const cookies = document.cookie.split(";");
            for (let cookie of cookies) {
                cookie = cookie.trim();
                if (cookie.startsWith(name + "=")) {
                    cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                    break;
                }
            }
        }
        return cookieValue;
    }

});