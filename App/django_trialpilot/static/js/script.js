document.addEventListener("DOMContentLoaded", function () {
    const modal = new bootstrap.Modal(document.getElementById("diaryModal"));
    const modalBody = document.getElementById("diaryModalBody");
    const confirmBtn = document.getElementById("confirmDiaryAction");

    document.querySelectorAll(".diary-card-trigger").forEach(card => {
        card.addEventListener("click", function (e) {


            if (e.target.classList.contains("diary-checkbox")) {
                return;
            }

            const diaryId = this.dataset.diaryId;
            const diaryTitle = this.dataset.diaryTitle;
            const extracted = this.dataset.diaryExtracted === "True";
            const detailsBtn = document.getElementById("diaryDetailsBtn");


            detailsBtn.href = `/diaries/${diaryId}/`;

            if (extracted) {
                modalBody.innerHTML = `
            <p>The diary <strong>${diaryTitle}</strong> has already been processed.</p>
            <p>It cannot be processed again.</p>
        `;
                confirmBtn.style.display = "none";

            } else {
                modalBody.innerHTML = `
            <p>The diary <strong>${diaryTitle}</strong> has not been processed yet.</p>
            <p>It will now be sent to the parameter extraction pipeline.</p>
        `;
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

        showPreview(files);
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
        showPreview(fileInput.files);
    });

    function showPreview(files) {
        const allowed = ["pdf", "txt"];
        const errorBox = document.getElementById("uploadError");

        preview.innerHTML = "";

        let hasError = false;

        Array.from(files).forEach(file => {
            const ext = file.name.split('.').pop().toLowerCase();

            if (!allowed.includes(ext)) {
                hasError = true;
                return;
            }

            let icon = "bi-file-earmark-text";
            if (ext === "pdf") icon = "bi-filetype-pdf";
            if (ext === "txt") icon = "bi-filetype-txt";

            preview.innerHTML += `
            <div class="d-flex align-items-center gap-2 mb-1">
                <i class="bi ${icon}" style="font-size:1.2rem;"></i>
                <span class="text-truncate" style="max-width: 220px;">${file.name}</span>
            </div>
        `;
        });

        if (hasError) {
            errorBox.classList.remove("d-none");
            errorBox.innerText = "Only PDF and TXT files are allowed.";
            fileInput.value = "";
            preview.innerHTML = "";
            progressContainer.style.display = "none";
            return;
        }

        errorBox.classList.add("d-none");
        progressContainer.style.display = "block";
        progressBar.style.width = "0%";
        progressText.innerText = `Ready to upload (${files.length} files)`;
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

document.addEventListener("DOMContentLoaded", function () {

    const patientModal = new bootstrap.Modal(document.getElementById("patientModal"));
    const patientBody = document.getElementById("patientModalBody");


    document.querySelectorAll(".patient-card-trigger").forEach(card => {
        card.addEventListener("click", function (e) {

            if (e.target.closest(".patient-actions")) {
                return;
            }

            const id = this.dataset.id;
            const age = this.dataset.age;
            const ecog = this.dataset.ecog;
            const diagnosis = this.dataset.diagnosis;
            const date = this.dataset.date;
            const molecular = this.dataset.molecular;
            const stage = this.dataset.stage;
            const control = this.dataset.control;

            const treatments = JSON.parse(this.dataset.treatments || "[]");

            let treatmentsHTML = "";

            if (treatments.length === 0) {
                treatmentsHTML = "<p class='text-muted'>No treatments available</p>";
            } else {
                treatmentsHTML = `
                <ul class="list-group">
                    ${treatments.map(t => `
                        <li class="list-group-item d-flex justify-content-between align-items-center">
                            <div>
                                <strong>${t.name}</strong><br>
                                <small>${t.start} → ${t.end || "Ongoing"}</small>
                            </div>
                        </li>
                    `).join("")}
                </ul>
            `;
            }

            patientBody.innerHTML = `
            <div class="container-fluid">
                <div class="row mb-3">
                    <div class="col">
                        <h5>Patient #${id}</h5>
                    </div>
                </div>

                <div class="row mb-2">
                    <div class="col-md-6"><strong>Age:</strong> ${age}</div>
                    <div class="col-md-6"><strong>ECOG:</strong> ${ecog}</div>
                </div>

                <div class="row mb-2">
                    <div class="col-md-6"><strong>Diagnosis:</strong> ${diagnosis}</div>
                    <div class="col-md-6"><strong>Date:</strong> ${date}</div>
                </div>

                <div class="row mb-2">
                    <div class="col-md-6"><strong>Molecular:</strong> ${molecular}</div>
                    <div class="col-md-6"><strong>Stage:</strong> ${stage}</div>
                </div>

                <div class="row mb-3">
                    <div class="col-md-12"><strong>Control:</strong> ${control}</div>
                </div>

                <hr>

                <h6 class="mb-2">Treatments</h6>
                ${treatmentsHTML}
            </div>
        `;

            patientModal.show();
        });
    });

});

function getCSRFToken() {
    return document.cookie
        .split('; ')
        .find(row => row.startsWith('csrftoken='))
        ?.split('=')[1];
}

document.addEventListener("DOMContentLoaded", function () {

    const checkboxes = document.querySelectorAll(".diary-checkbox");
    const deleteBtn = document.getElementById("deleteBtn");

    function updateDeleteButton() {
        const anyChecked = document.querySelectorAll(".diary-checkbox:checked").length > 0;
        deleteBtn.disabled = !anyChecked;
    }

    checkboxes.forEach(cb => {
        cb.addEventListener("change", updateDeleteButton);
    });

    const deleteModal = new bootstrap.Modal(document.getElementById("deleteModal"));
    const deleteModalBody = document.getElementById("deleteModalBody");
    const confirmDeleteBtn = document.getElementById("confirmDeleteBtn");

    let selectedDiaries = [];

    deleteBtn.addEventListener("click", function () {

        selectedDiaries = [];

        document.querySelectorAll(".diary-checkbox:checked").forEach(cb => {
            selectedDiaries.push(cb.value);
        });

        deleteModalBody.innerHTML = `
    <p>You are about to delete:</p>
    <ul>
        ${selectedDiaries.map(id => {
            const el = document.querySelector(`[value="${id}"]`)
                .closest(".diary-card-trigger");
            return `<li>${el.dataset.diaryTitle}</li>`;
        }).join("")}
    </ul>
    <p class="text-danger">This action cannot be undone.</p>
`;

        deleteModal.show();
    });

    confirmDeleteBtn.addEventListener("click", function () {

        const url = deleteBtn.dataset.url;

        fetch(url, {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "X-CSRFToken": getCSRFToken()
            },
            body: JSON.stringify({ diaries: selectedDiaries })
        })
            .then(res => res.json())
            .then(data => {
                deleteModal.hide();
                location.reload();
            });
    });
});

document.addEventListener("DOMContentLoaded", function () {

    const resetModal = new bootstrap.Modal(document.getElementById("resetModal"));
    const resetModalBody = document.getElementById("resetModalBody");
    const confirmResetBtn = document.getElementById("confirmResetBtn");

    let selectedPatientId = null;

    document.querySelectorAll(".reset-btn").forEach(btn => {
        btn.addEventListener("click", function (e) {

            e.stopPropagation();

            selectedPatientId = this.dataset.patientId

            resetModalBody.innerHTML = `
    <p>You are about to reset extraction for <strong>Patient #${selectedPatientId}</strong>.</p>
    <p>This will remove all generated data and versions.</p>
    <p class="text-danger">This action cannot be undone.</p>
`;

            resetModal.show();
        });
    });

    confirmResetBtn.addEventListener("click", function () {

        fetch(`/patients/${selectedPatientId}/reset`, {
            method: "POST",
            headers: {
                "X-CSRFToken": getCSRFToken()
            }
        })
            .then(res => res.json())
            .then(data => {
                resetModal.hide();
                location.reload();
            });
    });

});
