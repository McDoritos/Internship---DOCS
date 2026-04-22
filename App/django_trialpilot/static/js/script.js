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
        modalId: "trialUploadModal",
        dropZoneId: "trialDropZone",
        fileInputId: "trialFileInput",
        previewId: "trialFilePreview",
        errorId: "trialUploadError",
        progressContainerId: "trialProgressContainer",
        progressBarId: "trialProgressBar",
        progressTextId: "trialProgressText"
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
        progressTextId
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

            const files = e.dataTransfer.files;
            fileInput.files = files;

            showPreview(files);
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
            showPreview(fileInput.files);
        });

        function showPreview(files) {
            const allowed = ["pdf", "txt"];

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

    initBulkDelete({
        checkboxSelector: ".doc-checkbox",
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
        checkboxSelector: ".doc-checkbox",
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
            return Array.from(document.querySelectorAll(checkboxSelector)).filter(cb =>
                cb.closest(cardSelector)
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

    document.querySelectorAll(".add-condition").forEach(btn => {
        btn.addEventListener("click", function () {

            const logicId = this.dataset.logicId;
            const container = document.getElementById(`conditions_${logicId}`);
            const index = container.children.length + 1;

            const newRow = document.createElement("div");
            newRow.classList.add("row", "g-2", "align-items-center", "condition-row", "mb-2");

            newRow.innerHTML = `
                <div class="col-md-3">
                    <label class="form-label small text-muted">Field</label>
                    <select class="form-select logic-field" name="field_${logicId}_${index}">
                        <option value="">-- Select field --</option>
                        <option value="age" {% if logic.field == "age" %}selected{% endif %}>Age</option>
                        <option value="ecog_ps" {% if logic.field == "ecog_ps" %}selected{% endif %}>ECOG</option>
                        <option value="diagnosis" {% if logic.field == "diagnosis" %}selected{% endif %}>Diagnosis</option>
                        <option value="stage" {% if logic.field == "stage" %}selected{% endif %}>Stage</option>
                        <option value="molecular_status" {% if logic.field == "molecular_status" %}selected{% endif %}>Molecular Status</option>
                        <option value="sex" {% if logic.field == "sex" %}selected{% endif %}>Sex</option>
                        <option value="diagnosis_date" {% if logic.field == "diagnosis_date" %}selected{% endif %}>Diagnosis Date</option>
                        <option value="treatment" {% if logic.field == "treatment" %}selected{% endif %}>Treatment</option>
                        <option value="treatment_name" {% if logic.field == "treatment_name" %}selected{% endif %}>Treatment Name</option>
                        <option value="treatment_start_date" {% if logic.field == "treatment_start_date" %}selected{% endif %}>Treatment Start Date</option>
                        <option value="treatment_end_date" {% if logic.field == "treatment_end_date" %}selected{% endif %}>Treatment End Date</option>
                        <option value="progression_date" {% if logic.field == "progression_date" %}selected{% endif %}>Progression Date</option>
                        <option value="control" {% if logic.field == "control" %}selected{% endif %}>Control</option>
                        <option value="__custom__" {% if logic.field == "__custom__" %}selected{% endif %}>Other...</option>
                    </select>

                    <input type="text"
                        class="form-control mt-2 logic-field-custom"
                        name="field_custom_{{ logic.id }}"
                        id="field_custom_{{ logic.id }}"
                        value="{{ logic.custom_field }}"
                        placeholder="Enter custom field"
                        style="{% if logic.field == '__custom__' %}display: block;{% else %}display: none;{% endif %}">
                </div>

                <div class="col-md-3">
                    <label class="form-label small text-muted">Condition</label>
                    <select class="form-select logic-operator" name="operator_${logicId}_${index}">
                        <option value="">-- Select condition --</option>
                        <option value=">" {% if logic.operator == ">" %}selected{% endif %}>Greater than</option>
                        <option value="<" {% if logic.operator == "<" %}selected{% endif %}>Less than</option>
                        <option value="=" {% if logic.operator == "=" %}selected{% endif %}>Equals</option>
                        <option value=">=" {% if logic.operator == ">=" %}selected{% endif %}>Greater or equal</option>
                        <option value="<=" {% if logic.operator == "<=" %}selected{% endif %}>Less or equal</option>
                        <option value="contains" {% if logic.operator == "contains" %}selected{% endif %}>Contains</option>
                    </select>
                </div>

                <div class="col-md-5">
                    <label class="form-label small text-muted">Value</label>
                    <input type="text" 
                        class="form-control logic-value" 
                        name="value_${logicId}_${index}" 
                        placeholder="Enter value">
                </div>

                <div class="col-md-1">
                    <button type="button" class="btn btn-outline-danger btn-sm remove-condition">✕</button>
                </div>
            `;

            container.appendChild(newRow);
        });
    });

    document.addEventListener("click", function (e) {
        if (e.target.classList.contains("remove-condition")) {
            e.target.closest(".condition-row").remove();
        }
    });

});