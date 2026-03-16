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