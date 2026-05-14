document.addEventListener("DOMContentLoaded", function () {

    initCardModal({
        cardSelector: ".diary-card-trigger",
        modalId: "diaryModal",
        modalBodyId: "diaryModalBody",
        confirmBtnId: "confirmDiaryAction",
        detailsBtnId: "diaryDetailsBtn",
        dataPrefix: "diary",
        detailsBaseUrl: "/diaries/",
        actionBaseUrl: "/diaries/",
        actionPath: "extract",
        processedText: "processed",
        actionText: "parameter extraction pipeline"
    });

    initCardModal({
        cardSelector: ".trial-card-trigger",
        modalId: "trialModal",
        modalBodyId: "trialModalBody",
        confirmBtnId: "confirmTrialAction",
        detailsBtnId: "trialDetailsBtn",
        dataPrefix: "trial",
        detailsBaseUrl: "/trials/",
        actionBaseUrl: "/trials/",
        actionPath: "criteria-extract",
        processedText: "converted",
        actionText: "criteria conversion pipeline"
    });

    function initCardModal({
        cardSelector,
        modalId,
        modalBodyId,
        confirmBtnId,
        detailsBtnId,
        dataPrefix,
        detailsBaseUrl,
        actionBaseUrl,
        actionPath,
        processedText,
        actionText
    }) {
        const modalElement = document.getElementById(modalId);
        const modalBody = document.getElementById(modalBodyId);
        const confirmBtn = document.getElementById(confirmBtnId);
        const detailsBtn = document.getElementById(detailsBtnId);

        if (!modalElement || !modalBody || !confirmBtn || !detailsBtn) return;

        const modal = new bootstrap.Modal(modalElement);

        document.querySelectorAll(cardSelector).forEach(card => {
            card.addEventListener("click", function (e) {

                if (e.target.closest(".doc-checkbox, button, a, label, input")) {
                    return;
                }

                const itemId = this.dataset[`${dataPrefix}Id`];
                const itemTitle = this.dataset[`${dataPrefix}Title`];
                const extracted = this.dataset[`${dataPrefix}Extracted`]?.toLowerCase() === "true";

                detailsBtn.href = `${detailsBaseUrl}${itemId}/`;

                if (extracted) {
                    modalBody.innerHTML = `
                        <p>The ${dataPrefix} <strong>${itemTitle}</strong> has already been ${processedText}.</p>
                        <p>It cannot be processed again.</p>
                    `;
                    confirmBtn.style.display = "none";
                } else {
                    modalBody.innerHTML = `
                        <p>The ${dataPrefix} <strong>${itemTitle}</strong> has not been processed yet.</p>
                        <p>It will now be sent to the ${actionText}.</p>
                    `;
                    confirmBtn.style.display = "inline-block";
                    confirmBtn.href = `${actionBaseUrl}${itemId}/${actionPath}`;
                }

                modal.show();
            });
        });
    }

    const deleteBtn = document.getElementById("deleteBtn");
    const checkboxes = document.querySelectorAll(".doc-checkbox");

    function updateDeleteButtonState() {
        const checkedBoxes = document.querySelectorAll(".doc-checkbox:checked");
        if (deleteBtn) {
            deleteBtn.disabled = checkedBoxes.length === 0;
        }
    }

    checkboxes.forEach(checkbox => {
        checkbox.addEventListener("change", function () {
            const card = this.closest(".doc-card");

            if (card) {
                card.classList.toggle("selected-card", this.checked);
            }

            updateDeleteButtonState();
        });
    });

    updateDeleteButtonState();

});

document.addEventListener("DOMContentLoaded", function () {

    initUploadModal({
        formId: "uploadForm",
        modalId: "uploadModal",
        dropZoneId: "dropZone",
        fileInputId: "fileInput",
        previewId: "filePreview",
        errorId: "uploadError",
        progressContainerId: "progressContainer",
        progressBarId: "progressBar",
        progressTextId: "progressText"
    });

    initUploadModal({
        formId: "trialUploadForm",
        modalId: "uploadModal",
        dropZoneId: "trialDropZone",
        fileInputId: "trialFileInput",
        previewId: "trialFilePreview",
        errorId: "trialUploadError",
        progressContainerId: "trialProgressContainer",
        progressBarId: "trialProgressBar",
        progressTextId: "trialProgressText",
        singleFile: true,
        requireMetadata: true
    });

    function initUploadModal({
        formId,
        modalId,
        dropZoneId,
        fileInputId,
        previewId,
        errorId,
        progressContainerId,
        progressBarId,
        progressTextId,
        singleFile = false,
        requireMetadata = false
    }) {
        const form = document.getElementById(formId);
        const dropZone = document.getElementById(dropZoneId);
        const fileInput = document.getElementById(fileInputId);
        const preview = document.getElementById(previewId);

        const progressContainer = document.getElementById(progressContainerId);
        const progressBar = document.getElementById(progressBarId);
        const progressText = document.getElementById(progressTextId);

        const uploadModal = document.getElementById(modalId);
        const errorBox = document.getElementById(errorId);

        let trialTempFile = null;

        if (!dropZone || !form || !fileInput || !preview || !progressContainer || !progressBar || !progressText || !errorBox) return;

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

            let files = e.dataTransfer.files;

            if (singleFile && files.length > 1) {
                files = [files[0]];
            }

            const dt = new DataTransfer();
            Array.from(files).forEach(f => dt.items.add(f));
            fileInput.files = dt.files;

            if (singleFile && requireMetadata && fileInput.files.length > 0) {

                trialTempFile = fileInput.files[0];

                const uploadModalInstance = bootstrap.Modal.getInstance(uploadModal);
                if (uploadModalInstance) {
                    uploadModalInstance.hide();
                }

                const metadataModal = new bootstrap.Modal(document.getElementById("trialMetadataModal"));
                metadataModal.show();

                const nameBox = document.getElementById("selectedFileName");
                if (nameBox) {
                    nameBox.innerText = trialTempFile.name;
                }

                return;
            }

            showPreview(fileInput.files);
        });

        if (uploadModal) {
            uploadModal.addEventListener("hidden.bs.modal", () => {
                fileInput.value = "";
                preview.innerHTML = "";

                errorBox.classList.add("d-none");
                errorBox.innerText = "";

                progressContainer.style.display = "none";
                progressBar.style.width = "0%";
                progressText.innerText = "Uploading... 0%";

                dropZone.classList.remove("bg-light");
            });
        }

        fileInput.addEventListener("change", () => {

            if (singleFile && requireMetadata && fileInput.files.length > 0) {

                trialTempFile = fileInput.files[0];

                const uploadModalInstance = bootstrap.Modal.getInstance(uploadModal);
                if (uploadModalInstance) {
                    uploadModalInstance.hide();
                }

                const metadataModal = new bootstrap.Modal(document.getElementById("trialMetadataModal"));
                metadataModal.show();

                const nameBox = document.getElementById("selectedFileName");
                if (nameBox) {
                    nameBox.innerText = trialTempFile.name;
                }

                return;
            }

            showPreview(fileInput.files);
        });

        function showPreview(files) {
            const allowed = ["pdf", "txt"];

            preview.innerHTML = "";

            let hasError = false;

            let fileArray = Array.from(files);

            if (singleFile) {
                fileArray = fileArray.slice(0, 1);
            }

            fileArray.forEach(file => {
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

            if (singleFile) {
                progressText.innerText = `Ready to upload 1 file`;
            } else {
                progressText.innerText = `Ready to upload (${files.length} files)`;
            }
        }

        form.addEventListener("submit", function (e) {
            e.preventDefault();

            if (!fileInput.files.length) {
                alert("Please select a valid PDF or TXT file.");
                return;
            }

            if (requireMetadata) {
                const studyName = form.querySelector("[name='study_name']");
                const pathology = form.querySelector("[name='pathology_group']");
                const startDate = form.querySelector("[name='start_date']");
                const endDate = form.querySelector("[name='end_date']");
                const status = form.querySelector("[name='status']");

                if (!studyName.value || !pathology.value || !startDate.value || !status.value) {
                    alert("Please fill all required trial fields.");
                    return;
                }
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

        document.getElementById("trialMetadataForm").addEventListener("submit", function (e) {
            e.preventDefault();

            if (!trialTempFile) {
                alert("No file selected.");
                return;
            }

            const formData = new FormData();

            formData.append("file", trialTempFile);
            formData.append("type", "true");

            const form = e.target;

            formData.append("study_name", form.study_name.value);
            formData.append("pathology_group", form.pathology_group.value);
            formData.append("start_date", form.start_date.value);
            formData.append("end_date", form.end_date.value);
            formData.append("status", form.status.value);

            const xhr = new XMLHttpRequest();
            xhr.open("POST", document.getElementById("trialUploadForm").action, true);

            xhr.setRequestHeader("X-CSRFToken", getCookie("csrftoken"));

            xhr.onload = function () {
                if (xhr.status === 200) {
                    location.reload();
                } else {
                    alert("Upload failed");
                }
            };

            xhr.send(formData);
        });
    }

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

/* Patient Details */

document.addEventListener("DOMContentLoaded", function () {

    const patientModal = new bootstrap.Modal(document.getElementById("patientModal"));
    const patientBody = document.getElementById("patientModalBody");

    document.querySelectorAll(".view-patient-btn").forEach(btn => {
        btn.addEventListener("click", function (e) {
            e.stopPropagation();

            const card = this.closest(".patient-card-trigger");
            card.click();
        });
    });

    document.querySelectorAll(".patient-card-trigger").forEach(card => {
        card.addEventListener("click", function (e) {

            if (e.target.closest(".patient-actions")) {
                return;
            }

            const id = this.dataset.id;
            const age = this.dataset.age;
            const gender = this.dataset.gender;
            const ecog = this.dataset.ecog;
            const diagnosis = this.dataset.diagnosis;
            const date = this.dataset.date;
            const molecular = this.dataset.molecular;
            const stage = this.dataset.stage;
            const pathology_group = this.dataset.pathology_group;
            const control = this.dataset.control;

            const treatments = JSON.parse(this.dataset.treatments || "[]");
            let analysis = {};

            try {
                analysis = JSON.parse(this.dataset.analysis || "{}");
            } catch (e) {
                console.warn("Invalid analysis JSON:", this.dataset.analysis);
                analysis = {};
            }

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

            let analysisHTML = "";

            if (!analysis || Object.keys(analysis).length === 0) {
                analysisHTML = "<p class='text-muted'>No laboratory analysis available</p>";
            } else {

                const val = (v) => {
                    if (!v) return "-";
                    if (typeof v === "object") return v.value ?? "-";
                    return v;
                };


                const display = (obj) => {
                    if (!obj) return "-";
                    if (typeof obj === "object") {
                        const v = obj.value ?? "-";
                        const u = obj.unit ? ` ${obj.unit}` : "";
                        return `${v}${u}`;
                    }
                    return obj;
                };


                const valueBox = (label, value, extra = "") => `
    <div class="col-md-6 col-lg-4">
        <div class="rounded p-2 h-100 bg-white border">
            <div class="text-muted small">${label}</div>
            <div class="fw-semibold">
                ${value} ${extra}
            </div>
        </div>
    </div>
`;

                analysisHTML = `
<div class="mt-3">

    <!-- HEMATOLOGY -->
    <div class="card mb-3 shadow-sm border-0">
        <div class="card-header bg-primary-subtle text-primary py-2">
            <strong>Hematology</strong>
        </div>
        <div class="card-body bg-light-subtle">
            <div class="row g-2">
                ${valueBox("Leucocytes", display(analysis.leucocitos))}
${valueBox("Neutrophils", display(analysis.neutrofilos),
                    `<span class="badge bg-secondary-subtle text-secondary">${display(analysis.neutrofilos_percent)}</span>`)}
${valueBox("Lymphocytes", display(analysis.linfocitos),
                        `<span class="badge bg-secondary-subtle text-secondary">${display(analysis.linfocitos_percent)}</span>`)}
${valueBox("Monocytes", display(analysis.monocitos),
                            `<span class="badge bg-secondary-subtle text-secondary">${display(analysis.monocitos_percent)}</span>`)}
${valueBox("Eosinophils", display(analysis.eosinofilos),
                                `<span class="badge bg-secondary-subtle text-secondary">${display(analysis.eosinofilos_percent)}</span>`)}
${valueBox("Basophils", display(analysis.basofilos),
                                    `<span class="badge bg-secondary-subtle text-secondary">${display(analysis.basofilos_percent)}</span>`)}
            </div>
        </div>
    </div>

    <!-- ERYTHROCYTES -->
    <div class="card mb-3 shadow-sm border-0">
        <div class="card-header bg-danger-subtle text-danger py-2">
            <strong>Erythrocytes</strong>
        </div>
        <div class="card-body bg-light-subtle">
            <div class="row g-2">
                ${valueBox("RBC", display(analysis.eritrocitos))}
                ${valueBox("Hemoglobin", display(analysis.hemoglobina))}
                ${valueBox("Hematocrit", display(analysis.hematocrito))}
                ${valueBox("MCV", display(analysis.vc_medio))}
                ${valueBox("MCH", display(analysis.hcm))}
                ${valueBox("MCHC", display(analysis.chcm))}
                ${valueBox("RDW", display(analysis.rdw))}
            </div>
        </div>
    </div>

    <!-- PLATELETS -->
    <div class="card mb-3 shadow-sm border-0">
        <div class="card-header bg-warning-subtle text-warning py-2">
            <strong>Platelets</strong>
        </div>
        <div class="card-body bg-light-subtle">
            <div class="row g-2">
                ${valueBox("Platelets", display(analysis.plaquetas))}
                ${valueBox("MPV", display(analysis.vpm))}
                ${valueBox("PCT", display(analysis.plaquetocrito))}
                ${valueBox("PDW", display(analysis.pdw))}
            </div>
        </div>
    </div>

    <!-- BIOCHEMISTRY -->
    <div class="card mb-3 shadow-sm border-0">
        <div class="card-header bg-success-subtle text-success py-2">
            <strong>Biochemistry</strong>
        </div>
        <div class="card-body bg-light-subtle">
            <div class="row g-2">
                ${valueBox("Glucose", display(analysis.glicose))}
                ${valueBox("BUN", display(analysis.azoto_ureico))}
                ${valueBox("Creatinine", display(analysis.creatinina))}
                ${valueBox("Sodium", display(analysis.sodio))}
                ${valueBox("Potassium", display(analysis.potassio))}
                ${valueBox("Total Proteins", display(analysis.proteinas_totais))}
                ${valueBox("Albumin", display(analysis.albumina))}
                ${valueBox("Calcium", display(analysis.calcio))}
                ${valueBox("Osmolality", display(analysis.osmolalidade))}
                ${valueBox("LDH", display(analysis.ldh))}
                ${valueBox("AST", display(analysis.ast))}
                ${valueBox("ALT", display(analysis.alt))}
                ${valueBox("ALP", display(analysis.fosfatase_alcalina))}
                ${valueBox("GGT", display(analysis.gama_gt))}
                ${valueBox("Bilirubin", display(analysis.bilirrubina_total))}
                ${valueBox("CK", display(analysis.creatina_cinase))}
            </div>
        </div>
    </div>

</div>
`;

            }

            patientBody.innerHTML = `
<div class="container-fluid">

    <!-- HEADER -->
<div class="d-flex justify-content-between align-items-center mb-3">
    <h5 class="mb-0">Patient #${id}</h5>
</div>

<!-- PATIENT OVERVIEW -->
<div class="card shadow-sm border-0 mb-4">
    <div class="card-header bg-light-subtle py-2">
        <strong>Patient Overview</strong>
    </div>
    <div class="card-body">
        <div class="row g-3">

            <!-- LINE 1 -->
            <div class="col-md-4">
                <div class="text-muted small">Age</div>
                <div class="fw-semibold fs-5">${age || "-"}</div>
            </div>

            <div class="col-md-4">
                <div class="text-muted small">Diagnosis Date</div>
                <div class="fw-semibold fs-5">${date || "-"}</div>
            </div>

            <div class="col-md-4">
                <div class="text-muted small">ECOG</div>
                <span class="badge bg-primary-subtle text-primary fs-5" style="padding: 0 !important;">
                    ${ecog || "-"}
                </span>
            </div>

            <!-- LINE 2 -->
            <div class="col-md-4">
                <div class="text-muted small">Stage</div>
                <span class="badge bg-warning-subtle text-warning fs-5" style="padding: 0 !important;">
                    ${stage || "-"}
                </span>
            </div>

            <div class="col-md-4">
                <div class="text-muted small">Pathology Group</div>
                <span class="badge bg-info-subtle text-info fs-5" style="padding: 0 !important;">
                    ${pathology_group || "-"}
                </span>
            </div>

            <!-- EMPTY COLUMN FOR ALIGNMENT -->
            <div class="col-md-4">
                <div class="text-muted small">Gender</div>
                <div class="fw-semibold fs-5">${gender || "-"}</div>
            </div>

            <!-- LINE 3 -->
            <div class="col-12">
                <div class="text-muted small">Diagnosis</div>
                <div class="fw-semibold">${diagnosis || "-"}</div>
            </div>

        </div>
    </div>
</div>



<!-- CLINICAL DETAILS -->
<div class="card shadow-sm border-0 mb-4">
    <div class="card-header bg-light-subtle py-2">
        <strong>Clinical Details</strong>
    </div>
    <div class="card-body">
        <div class="row g-3">

            <!-- Molecular -->
            <div class="col-md-6">
                <div class="text-muted small">Molecular Status</div>
                <div class="fw-semibold">${molecular || "-"}</div>
            </div>

            <!-- Control (full width) -->
            <div class="col-12 mt-2">
                <div class="text-muted small mb-1">Clinical Control / Follow-up</div>
                <div class="fw-semibold">${control || "-"}</div>
            </div>

        </div>
    </div>
</div>


    <!-- TREATMENTS -->
    <div class="mb-3">
        <h6 class="mb-2">Treatments</h6>
        ${treatmentsHTML}
    </div>

    <!-- LABORATORY ANALYSIS -->
    <div class="mt-4">
        <h6 class="mb-2">Laboratory Analysis</h6>
        ${analysisHTML}
    </div>

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

    initBulkDelete({
        checkboxSelector: ".doc-checkbox, .diary-checkbox",
        deleteBtnId: "deleteBtn",
        deleteModalId: "deleteModal",
        deleteModalBodyId: "deleteModalBody",
        confirmDeleteBtnId: "confirmDeleteBtn",
        cardSelector: ".diary-card-trigger",
        datasetTitleKey: "diaryTitle",
        payloadKey: "diaries",
        itemLabel: "diaries"
    });

    initBulkDelete({
        checkboxSelector: ".doc-checkbox, .trial-checkbox",
        deleteBtnId: "deleteBtn",
        deleteModalId: "deleteModal",
        deleteModalBodyId: "deleteModalBody",
        confirmDeleteBtnId: "confirmDeleteBtn",
        cardSelector: ".trial-card-trigger",
        datasetTitleKey: "trialTitle",
        payloadKey: "trials",
        itemLabel: "trials"
    });

    function initBulkDelete({
        checkboxSelector,
        deleteBtnId,
        deleteModalId,
        deleteModalBodyId,
        confirmDeleteBtnId,
        cardSelector,
        datasetTitleKey,
        payloadKey,
        itemLabel
    }) {
        const deleteBtn = document.getElementById(deleteBtnId);
        const deleteModalElement = document.getElementById(deleteModalId);
        const deleteModalBody = document.getElementById(deleteModalBodyId);
        const confirmDeleteBtn = document.getElementById(confirmDeleteBtnId);

        if (!deleteBtn || !deleteModalElement || !deleteModalBody || !confirmDeleteBtn) return;

        const matchingCards = document.querySelectorAll(cardSelector);
        if (!matchingCards.length) return;

        const deleteModal = new bootstrap.Modal(deleteModalElement);
        let selectedItems = [];

        function getMatchingCheckboxes() {

            const selectors = checkboxSelector
                .split(",")
                .map(s => s.trim());

            return selectors.flatMap(selector =>
                Array.from(document.querySelectorAll(selector))
                    .filter(cb => cb.closest(cardSelector))
            );
        }

        function updateDeleteButton() {
            const anyChecked = getMatchingCheckboxes().some(cb => cb.checked);
            deleteBtn.disabled = !anyChecked;
        }

        getMatchingCheckboxes().forEach(cb => {
            cb.addEventListener("change", updateDeleteButton);
        });

        deleteBtn.addEventListener("click", function () {
            selectedItems = [];

            getMatchingCheckboxes()
                .filter(cb => cb.checked)
                .forEach(cb => selectedItems.push(cb.value));

            deleteModalBody.innerHTML = `
                <p>You are about to delete:</p>
                <ul>
                    ${selectedItems.map(id => {
                const checkbox = document.querySelector(`${checkboxSelector}[value="${id}"]`);
                const card = checkbox?.closest(cardSelector);
                const title = card?.dataset?.[datasetTitleKey] || `Item ${id}`;
                return `<li>${title}</li>`;
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
                body: JSON.stringify({ [payloadKey]: selectedItems })
            })
                .then(res => res.json())
                .then(data => {
                    deleteModal.hide();
                    location.reload();
                })
                .catch(err => {
                    console.error(`Error deleting ${itemLabel}:`, err);
                });
        });

        updateDeleteButton();
    }

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


/* Trial Criteria Extraction */
document.addEventListener("DOMContentLoaded", function () {

    function updateNumbers(containerId, countId) {
        const container = document.getElementById(containerId);
        const count = document.getElementById(countId);
        const items = container.querySelectorAll(".criterion-item");

        items.forEach((item, index) => {
            const number = item.querySelector(".criterion-number");
            if (number) number.textContent = index + 1;
        });

        count.textContent = items.length;
    }

    function removeEmptyState(container) {
        const empty = container.querySelector(".empty-mini");
        if (empty) empty.remove();
    }

    function ensureEmptyState(containerId, message) {
        const container = document.getElementById(containerId);
        const items = container.querySelectorAll(".criterion-item");

        if (items.length === 0 && !container.querySelector(".empty-mini")) {
            const empty = document.createElement("div");
            empty.className = "empty-mini text-muted";
            empty.textContent = message;
            container.appendChild(empty);
        }
    }

    document.querySelectorAll(".add-field").forEach(button => {
        button.addEventListener("click", function () {
            const container = document.getElementById(this.dataset.target);
            const fieldName = this.dataset.name;
            const placeholder = this.dataset.placeholder || "Write criterion...";

            removeEmptyState(container);

            const wrapper = document.createElement("div");
            wrapper.className = "criterion-item";

            const itemCount = container.querySelectorAll(".criterion-item").length + 1;

            wrapper.innerHTML = `
                <div class="criterion-number">${itemCount}</div>
                <input type="text" name="${fieldName}" class="form-control criterion-input" placeholder="${placeholder}">
                <button type="button" class="btn btn-icon btn-remove remove-field" title="Remove criterion">
                    <i class="bi bi-trash"></i>
                </button>
            `;

            container.appendChild(wrapper);
            wrapper.querySelector("input").focus();

            if (container.id === "inclusion-container") {
                updateNumbers("inclusion-container", "inclusion-count");
            } else if (container.id === "exclusion-container") {
                updateNumbers("exclusion-container", "exclusion-count");
            }
        });
    });

    document.addEventListener("click", function (e) {
        const removeBtn = e.target.closest(".remove-field");
        if (!removeBtn) return;

        const item = removeBtn.closest(".criterion-item");
        const container = item.parentElement;
        item.remove();

        if (container.id === "inclusion-container") {
            updateNumbers("inclusion-container", "inclusion-count");
            ensureEmptyState("inclusion-container", "No inclusion criteria extracted.");
        } else if (container.id === "exclusion-container") {
            updateNumbers("exclusion-container", "exclusion-count");
            ensureEmptyState("exclusion-container", "No exclusion criteria extracted.");
        }
    });

    updateNumbers("inclusion-container", "inclusion-count");
    updateNumbers("exclusion-container", "exclusion-count");
});

/* Diary Parameter Extraction */
document.addEventListener("DOMContentLoaded", function () {
    const treatmentContainer = document.getElementById("treatment-container");
    const treatmentCount = document.getElementById("treatment-count");

    function updateTreatmentNumbers() {
        const treatments = treatmentContainer.querySelectorAll(".treatment-card");
        treatments.forEach((card, index) => {
            const number = card.querySelector(".treatment-number");
            if (number) number.textContent = index + 1;
        });
        treatmentCount.textContent = treatments.length;
    }

    function ensureTreatmentEmptyState() {
        const treatments = treatmentContainer.querySelectorAll(".treatment-card");
        const emptyState = document.getElementById("treatment-empty");

        if (treatments.length === 0 && !emptyState) {
            const empty = document.createElement("div");
            empty.className = "empty-mini text-muted";
            empty.id = "treatment-empty";
            empty.textContent = "No treatments extracted.";
            treatmentContainer.appendChild(empty);
        }
    }

    function removeTreatmentEmptyState() {
        const empty = document.getElementById("treatment-empty");
        if (empty) empty.remove();
    }

    document.getElementById("add-treatment").addEventListener("click", function () {
        removeTreatmentEmptyState();

        const currentCount = treatmentContainer.querySelectorAll(".treatment-card").length + 1;

        const wrapper = document.createElement("div");
        wrapper.className = "treatment-card";

        wrapper.innerHTML = `
            <div class="d-flex justify-content-between align-items-center mb-3">
                <div class="treatment-title">
                    <i class="bi bi-activity me-2"></i>
                    Treatment <span class="treatment-number">${currentCount}</span>
                </div>
                <button type="button" class="btn btn-icon btn-remove remove-treatment" title="Remove treatment">
                    <i class="bi bi-trash"></i>
                </button>
            </div>

            <div class="row g-3">
                <div class="col-md-12">
                    <label class="form-label field-label">Treatment Name</label>
                    <input type="text" name="treatment_name[]" class="form-control clinical-input" placeholder="Enter treatment name...">
                </div>

                <div class="col-md-6">
                    <label class="form-label field-label">Start Date</label>
                    <input type="text" name="treatment_start_date[]" class="form-control clinical-input" placeholder="e.g. 2023-05-01">
                </div>

                <div class="col-md-6">
                    <label class="form-label field-label">End Date</label>
                    <input type="text" name="treatment_end_date[]" class="form-control clinical-input" placeholder="e.g. 2023-10-15">
                </div>
            </div>
        `;

        treatmentContainer.appendChild(wrapper);
        wrapper.querySelector("input").focus();
        updateTreatmentNumbers();
    });

    document.addEventListener("click", function (e) {
        const removeBtn = e.target.closest(".remove-treatment");
        if (!removeBtn) return;

        const card = removeBtn.closest(".treatment-card");
        card.remove();

        updateTreatmentNumbers();
        ensureTreatmentEmptyState();
    });

    updateTreatmentNumbers();
});

/* Trial Criteria Conversion */

document.addEventListener("DOMContentLoaded", function () {
    const form = document.querySelector("form");
    const jsonInputs = document.querySelectorAll(".logic-json-input");

    document.querySelectorAll(".logic-builder").forEach(builder => {
        const select = builder.querySelector(".logic-field");
        const input = builder.querySelector(".logic-field-custom");

        if (!select || !input) return;

        function toggleCustomField() {
            if (select.value === "__custom__") {
                input.style.display = "block";
            } else {
                input.style.display = "none";
                input.value = "";
            }
        }

        toggleCustomField();

        select.addEventListener("change", toggleCustomField);
    });

    function createFeedbackElement(input) {
        let feedback = input.parentElement.querySelector(".json-feedback");

        if (!feedback) {
            feedback = document.createElement("div");
            feedback.className = "json-feedback mt-2 small";
            input.parentElement.appendChild(feedback);
        }

        return feedback;
    }

    function markValid(input, message = "Valid JSON structure.") {
        const feedback = createFeedbackElement(input);

        input.classList.remove("is-invalid");
        input.classList.add("is-valid");

        feedback.classList.remove("text-danger");
        feedback.classList.add("text-success");
        feedback.innerHTML = `<i class="bi bi-check-circle me-1"></i>${message}`;
    }

    function markInvalid(input, message = "Invalid JSON.") {
        const feedback = createFeedbackElement(input);

        input.classList.remove("is-valid");
        input.classList.add("is-invalid");

        feedback.classList.remove("text-success");
        feedback.classList.add("text-danger");
        feedback.innerHTML = `<i class="bi bi-exclamation-triangle me-1"></i>${message}`;
    }

    function formatJSON(input) {
        const value = input.value.trim();

        if (!value) {
            markInvalid(input, "This field cannot be empty.");
            return false;
        }

        try {
            const parsed = JSON.parse(value);
            input.value = JSON.stringify(parsed, null, 2);
            markValid(input);
            return true;
        } catch (error) {
            markInvalid(input, error.message);
            return false;
        }
    }

    function validateJSON(input) {
        const value = input.value.trim();

        if (!value) {
            markInvalid(input, "This field cannot be empty.");
            return false;
        }

        try {
            JSON.parse(value);
            markValid(input);
            return true;
        } catch (error) {
            markInvalid(input, error.message);
            return false;
        }
    }

    function validateAllJSON() {
        let allValid = true;

        jsonInputs.forEach(input => {
            const isValid = validateJSON(input);
            if (!isValid) allValid = false;
        });

        return allValid;
    }

    jsonInputs.forEach(input => {
        validateJSON(input);

        input.addEventListener("blur", function () {
            validateJSON(input);
        });

        input.addEventListener("input", function () {
            input.classList.remove("is-valid", "is-invalid");

            const feedback = input.parentElement.querySelector(".json-feedback");
            if (feedback) {
                feedback.innerHTML = "";
            }
        });

        input.addEventListener("keydown", function (e) {
            // TAB support inside textarea
            if (e.key === "Tab") {
                e.preventDefault();

                const start = this.selectionStart;
                const end = this.selectionEnd;

                this.value = this.value.substring(0, start) + "  " + this.value.substring(end);
                this.selectionStart = this.selectionEnd = start + 2;
            }

            // Ctrl/Cmd + Shift + F => format JSON
            if ((e.ctrlKey || e.metaKey) && e.shiftKey && e.key.toLowerCase() === "f") {
                e.preventDefault();
                formatJSON(this);
            }
        });
    });

    form.addEventListener("submit", function (e) {
        const allValid = validateAllJSON();

        if (!allValid) {
            e.preventDefault();

            const firstInvalid = document.querySelector(".logic-json-input.is-invalid");
            if (firstInvalid) {
                firstInvalid.scrollIntoView({
                    behavior: "smooth",
                    block: "center"
                });
                firstInvalid.focus();
            }

            showToast("Please fix invalid JSON fields before continuing.", "danger");
        } else {
            jsonInputs.forEach(input => formatJSON(input));
        }
    });

    function showToast(message, type = "success") {
        let toastContainer = document.getElementById("toast-container");

        if (!toastContainer) {
            toastContainer = document.createElement("div");
            toastContainer.id = "toast-container";
            toastContainer.className = "toast-container position-fixed top-0 end-0 p-3";
            toastContainer.style.zIndex = "1080";
            document.body.appendChild(toastContainer);
        }

        const toast = document.createElement("div");
        toast.className = `toast align-items-center text-bg-${type} border-0 show mb-2`;
        toast.setAttribute("role", "alert");
        toast.innerHTML = `
            <div class="d-flex">
                <div class="toast-body">
                    ${message}
                </div>
                <button type="button" class="btn-close btn-close-white me-2 m-auto" aria-label="Close"></button>
            </div>
        `;

        toastContainer.appendChild(toast);

        toast.querySelector(".btn-close").addEventListener("click", () => {
            toast.remove();
        });

        setTimeout(() => {
            toast.remove();
        }, 4000);
    }

});

document.addEventListener("DOMContentLoaded", function () {

    // REMOVE CONDITION
    document.addEventListener("click", function (e) {
        if (e.target.classList.contains("remove-condition")) {
            e.target.closest(".condition-row").remove();
        }
    });

    document.addEventListener("change", function (e) {

        if (e.target.classList.contains("logic-field")) {

            const row = e.target.closest(".condition-row");
            const customInput = row.querySelector(".logic-field-custom");

            if (e.target.value === "__custom__") {
                customInput.style.display = "block";
            } else {
                customInput.style.display = "none";
                customInput.value = "";
            }
        }
    });

    document.addEventListener("click", function (e) {

        // ADD CONDITION
        if (e.target.classList.contains("add-condition")) {

            const container = e.target.closest(".nested-group")
                ? e.target.closest(".nested-group").querySelector(".conditions-container")
                : document.getElementById(`conditions_${e.target.dataset.logicId}`);

            const template = document.getElementById("condition-template");
            const clone = template.content.cloneNode(true);

            container.appendChild(clone);

            const newWrapper = container.lastElementChild;
            const newRow = newWrapper.querySelector(".condition-row");

            if (newRow) {
                toggleUnitField(newRow);

                const fieldSelect = newRow.querySelector(".logic-field");

                if (fieldSelect) {
                    fieldSelect.addEventListener("change", () => {
                        toggleUnitField(newRow);
                    });
                }
            }
        }

        // ADD GROUP
        if (e.target.classList.contains("add-group")) {

            const container = e.target.closest(".nested-group")
                ? e.target.closest(".nested-group").querySelector(".conditions-container")
                : document.getElementById(`conditions_${e.target.dataset.logicId}`);

            const template = document.getElementById("group-template");
            const clone = template.content.cloneNode(true);

            container.appendChild(clone);
        }

        // REMOVE CONDITION
        if (e.target.classList.contains("remove-condition")) {
            e.target.closest(".condition-row").remove();
        }

        // REMOVE GROUP
        if (e.target.classList.contains("remove-group")) {
            e.target.closest(".nested-group").remove();
        }
    });

    function toggleUnitField(row) {

        const fieldSelect = row.querySelector(".logic-field");
        const unitWrapper = row.querySelector(".unit-wrapper");

        if (!fieldSelect || !unitWrapper) return;

        const selectedOption =
            fieldSelect.options[fieldSelect.selectedIndex];

        const isLabField =
            selectedOption.dataset.labField === "true";

        if (isLabField) {
            unitWrapper.style.display = "block";
        } else {
            unitWrapper.style.display = "none";

            const input = unitWrapper.querySelector("input");
            if (input) input.value = "";
        }
    }

    document.querySelectorAll(".condition-row").forEach(row => {
        toggleUnitField(row);

        const fieldSelect = row.querySelector(".logic-field");

        if (fieldSelect) {
            fieldSelect.addEventListener("change", () => {
                toggleUnitField(row);
            });
        }
    });

});

/* PATIENT MATCHING */ 
document.addEventListener("DOMContentLoaded", function () {

    window.setCriterionOverride = function (patientId, criterionId, decision, button) {
        const criterionCard = button.closest(".criterion-card");
        const criterionType = criterionCard.dataset.type;
        const criterionText = criterionCard.dataset.text; 
        
        const previousResult = criterionCard.dataset.result === "true";
        let newResult;

        if (criterionType === "inclusion") {
            console.log("INCLUSION triggered → decision:", decision);
            newResult = (decision === "pass");
        } else {
            console.log("EXCLUSION triggered → decision:", decision);

            newResult = (decision === "fail"); 
        }

        if (previousResult === newResult) return;

        criterionCard.dataset.result = newResult;

        const headerDiv = criterionCard.querySelector(".criterion-header-content");
        
        if (criterionType === "inclusion") {
            if (newResult) {
                headerDiv.innerHTML = `<i class="criterion-status-icon bi bi-check-circle-fill text-success"></i> <strong>${criterionText}</strong>`;
            } else {
                headerDiv.innerHTML = `<i class="criterion-status-icon bi bi-x-circle-fill text-danger"></i> <strong>${criterionText}</strong>`;
            }
        } else {
            if (newResult) {
                headerDiv.innerHTML = `<i class="criterion-status-icon bi bi-exclamation-circle-fill text-danger"></i> <strong>Triggered:</strong> ${criterionText}`;
            } else {
                headerDiv.innerHTML = `<i class="criterion-status-icon bi bi-check-circle-fill text-success"></i> ${criterionText}`;
            }
        }

        const actions = button.parentElement;
        actions.querySelectorAll(".decision-btn").forEach(btn => btn.classList.remove("active"));
        button.classList.add("active");

        const inclusionElement = document.getElementById(`inclusion-count-${patientId}`);
        const exclusionElement = document.getElementById(`exclusion-count-${patientId}`);
        let inclusionCurrent = parseInt(inclusionElement.dataset.current);
        let exclusionCurrent = parseInt(exclusionElement.dataset.current);

        if (criterionType === "inclusion") {
            newResult ? inclusionCurrent++ : inclusionCurrent--;
            inclusionElement.dataset.current = inclusionCurrent;
            inclusionElement.innerText = `${inclusionCurrent}/${inclusionElement.dataset.total}`;
        } else {
            newResult ? exclusionCurrent++ : exclusionCurrent--;
            exclusionCurrent = Math.max(0, exclusionCurrent);
            exclusionElement.dataset.current = exclusionCurrent;
            exclusionElement.innerText = exclusionCurrent;
        }

        const inclusionTotal = parseInt(inclusionElement.dataset.total);
        const isEligible = (inclusionCurrent === inclusionTotal) && (exclusionCurrent === 0);
        const badge = document.getElementById(`eligibility-badge-${patientId}`);
        const wasEligible = badge.innerText.trim() === "Eligible";

        badge.className = `badge ${isEligible ? 'bg-success' : 'bg-danger'} px-3 py-2 text-white rounded-ui`;
        badge.innerText = isEligible ? "Eligible" : "Ineligible";

        if (wasEligible !== isEligible) {
            const eSummary = document.getElementById("eligible-count");
            const iSummary = document.getElementById("ineligible-count");
            let eCount = parseInt(eSummary.innerText);
            let iCount = parseInt(iSummary.innerText);
            isEligible ? (eCount++, iCount--) : (eCount--, iCount++);
            eSummary.innerText = eCount;
            iSummary.innerText = iCount;
        }

        let decisionToSave = decision;
        if (criterionType === "exclusion") {
            decisionToSave = (decision === "pass") ? "fail" : "pass";
        }

        const container = document.getElementById("manual-overrides-container");
        const inputId = `override-${patientId}-${criterionId}`;
        let input = document.getElementById(inputId);
        if (!input) {
            input = document.createElement("input");
            input.type = "hidden";
            input.name = "overrides";
            input.id = inputId;
            container.appendChild(input);
        }
        input.value = JSON.stringify({ 
            patient_id: patientId, 
            criterion_id: criterionId, 
            decision: decisionToSave
        });
    };
});