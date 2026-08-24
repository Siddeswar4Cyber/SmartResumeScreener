const MAX_FILES = 5;
const MAX_FILE_SIZE = 5 * 1024 * 1024;
const ALLOWED_EXTENSIONS = new Set(["pdf", "txt"]);

const state = {
    jobs: [],
    selectedJobId: null,
    rankings: [],
    selectedCandidate: null,
    selectedFiles: [],
    searchTerm: "",
    lastFocusedElement: null,
    loading: {
        jobs: false,
        createJob: false,
        deleteJob: false,
        results: false,
        screening: false,
        candidate: false,
        rescreen: false,
        deleteCandidate: false,
    },
    requestIds: {
        jobs: 0,
        results: 0,
        candidate: 0,
    },
};

const elements = {
    appMessage: document.querySelector("#app-message"),
    totalJobs: document.querySelector("#stat-total-jobs"),
    candidateStat: document.querySelector("#stat-candidates"),
    strongMatchStat: document.querySelector("#stat-strong-matches"),
    averageScoreStat: document.querySelector("#stat-average-score"),
    jobForm: document.querySelector("#job-form"),
    titleInput: document.querySelector("#job-title"),
    descriptionInput: document.querySelector("#job-description"),
    descriptionCount: document.querySelector("#job-description-count"),
    createJobButton: document.querySelector("#create-job-button"),
    formMessage: document.querySelector("#form-message"),
    jobSearch: document.querySelector("#job-search"),
    refreshJobsButton: document.querySelector("#refresh-jobs-button"),
    jobsMessage: document.querySelector("#jobs-message"),
    jobsList: document.querySelector("#jobs-list"),
    selectedJobMeta: document.querySelector("#selected-job-meta"),
    deleteJobButton: document.querySelector("#delete-job-button"),
    jobDetails: document.querySelector("#job-details"),
    uploadJobContext: document.querySelector("#upload-job-context"),
    dropZone: document.querySelector("#drop-zone"),
    fileInput: document.querySelector("#resume-files"),
    clearFilesButton: document.querySelector("#clear-files-button"),
    screenResumesButton: document.querySelector("#screen-resumes-button"),
    uploadMessage: document.querySelector("#upload-message"),
    selectedFiles: document.querySelector("#selected-files"),
    screeningOutcome: document.querySelector("#screening-outcome"),
    candidateCount: document.querySelector("#candidate-count"),
    resultsJobTitle: document.querySelector("#results-job-title"),
    refreshResultsButton: document.querySelector("#refresh-results-button"),
    resultsMessage: document.querySelector("#results-message"),
    resultsList: document.querySelector("#results-list"),
    candidateModal: document.querySelector("#candidate-modal"),
    candidateDialog: document.querySelector("#candidate-dialog"),
    candidateDialogTitle: document.querySelector("#candidate-dialog-title"),
    closeCandidateButton: document.querySelector("#close-candidate-button"),
    candidateMessage: document.querySelector("#candidate-message"),
    candidateDetailContent: document.querySelector("#candidate-detail-content"),
    rescreenCandidateButton: document.querySelector("#rescreen-candidate-button"),
    deleteCandidateButton: document.querySelector("#delete-candidate-button"),
};

class ApiError extends Error {
    constructor(message, status, data = null) {
        super(message);
        this.name = "ApiError";
        this.status = status;
        this.data = data;
    }
}

function createElement(tagName, className = "", text = null) {
    const element = document.createElement(tagName);
    if (className) {
        element.className = className;
    }
    if (text !== null) {
        element.textContent = text;
    }
    return element;
}

function clearElement(element) {
    element.textContent = "";
}

function setMessage(element, message = "", type = "") {
    element.textContent = message;
    element.className = `message ${type}`.trim();
}

function errorText(error, fallback) {
    return error instanceof Error && error.message
        ? error.message
        : fallback;
}

function statusFallback(status) {
    const messages = {
        404: "The requested record was not found.",
        422: "The submitted data could not be processed.",
        429: "Too many requests. Wait a moment and try again.",
        500: "The server encountered an error. Try again later.",
        502: "The screening service is temporarily unavailable.",
    };
    return messages[status] || `Request failed (${status}).`;
}

function getErrorMessage(data, status) {
    const detail = data && typeof data === "object" ? data.detail : null;

    if (typeof detail === "string" && detail.trim()) {
        return detail.trim();
    }

    if (Array.isArray(detail)) {
        const messages = detail
            .map((item) => {
                if (typeof item === "string" && item.trim()) {
                    return item.trim();
                }
                if (!item || typeof item.msg !== "string") {
                    return null;
                }
                const location = Array.isArray(item.loc) && item.loc.length > 0
                    ? item.loc[item.loc.length - 1]
                    : null;
                return location
                    ? `${String(location)}: ${item.msg}`
                    : item.msg;
            })
            .filter(Boolean);

        if (messages.length > 0) {
            return messages.join(" ");
        }
    }

    if (detail && typeof detail === "object") {
        if (typeof detail.message === "string" && detail.message.trim()) {
            return detail.message.trim();
        }
        if (typeof detail.error === "string" && detail.error.trim()) {
            return detail.error.trim();
        }
    }

    if (data && typeof data.message === "string" && data.message.trim()) {
        return data.message.trim();
    }

    return statusFallback(status);
}

async function apiRequest(url, options = {}) {
    let response;

    try {
        response = await fetch(url, options);
    } catch {
        throw new ApiError(
            "Unable to reach the server. Check your connection and try again.",
            0,
        );
    }

    const responseText = await response.text();
    let data = null;

    if (responseText) {
        try {
            data = JSON.parse(responseText);
        } catch {
            if (!response.ok) {
                throw new ApiError(statusFallback(response.status), response.status);
            }
            throw new ApiError(
                "The server returned a response that was not valid JSON.",
                response.status,
            );
        }
    }

    if (!response.ok) {
        throw new ApiError(
            getErrorMessage(data, response.status),
            response.status,
            data,
        );
    }

    return data;
}

function safeText(value, fallback = "Not available") {
    if (typeof value === "string" && value.trim()) {
        return value.trim();
    }
    if (typeof value === "number" && Number.isFinite(value)) {
        return String(value);
    }
    return fallback;
}

function safeStringList(value) {
    if (!Array.isArray(value)) {
        return [];
    }
    return value
        .filter((item) => typeof item === "string" && item.trim())
        .map((item) => item.trim());
}

function valueAsList(value) {
    if (Array.isArray(value)) {
        return safeStringList(value);
    }
    if (typeof value === "string" && value.trim()) {
        return [value.trim()];
    }
    return [];
}

function formatDate(value) {
    if (typeof value !== "string" || !value.trim()) {
        return "Not available";
    }
    const normalized = value.includes("T") ? value : `${value.replace(" ", "T")}Z`;
    const parsed = new Date(normalized);
    if (Number.isNaN(parsed.getTime())) {
        return value;
    }
    return parsed.toLocaleString([], {
        dateStyle: "medium",
        timeStyle: "short",
    });
}

function formatFileSize(bytes) {
    if (!Number.isFinite(bytes) || bytes < 0) {
        return "Unknown size";
    }
    if (bytes < 1024) {
        return `${bytes} B`;
    }
    if (bytes < 1024 * 1024) {
        return `${(bytes / 1024).toFixed(1)} KB`;
    }
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function getSelectedJob() {
    return state.jobs.find((job) => job.id === state.selectedJobId) || null;
}

function jobInteractionLocked() {
    return state.loading.screening || state.loading.deleteJob;
}

function updateControlStates() {
    const selectedJob = getSelectedJob();
    const locked = jobInteractionLocked();
    const filesAvailable = state.selectedFiles.length > 0;

    elements.titleInput.disabled = state.loading.createJob || locked;
    elements.descriptionInput.disabled = state.loading.createJob || locked;
    elements.createJobButton.disabled = state.loading.createJob || locked;
    elements.refreshJobsButton.disabled = state.loading.jobs || locked;
    elements.jobSearch.disabled = locked;

    elements.deleteJobButton.hidden = !selectedJob;
    elements.deleteJobButton.disabled = !selectedJob || locked;

    elements.fileInput.disabled = !selectedJob || state.loading.screening;
    elements.clearFilesButton.disabled = !filesAvailable || state.loading.screening;
    elements.screenResumesButton.disabled = (
        !selectedJob || !filesAvailable || state.loading.screening
    );
    elements.dropZone.classList.toggle(
        "disabled",
        !selectedJob || state.loading.screening,
    );

    elements.refreshResultsButton.disabled = (
        !selectedJob || state.loading.results || state.loading.screening
    );

    const candidateAvailable = Boolean(state.selectedCandidate);
    elements.rescreenCandidateButton.disabled = (
        !candidateAvailable
        || state.loading.rescreen
        || state.loading.deleteCandidate
    );
    elements.deleteCandidateButton.disabled = (
        !candidateAvailable
        || state.loading.rescreen
        || state.loading.deleteCandidate
    );

    for (const button of elements.jobsList.querySelectorAll("button")) {
        button.disabled = locked;
    }

    elements.jobForm.setAttribute("aria-busy", String(state.loading.createJob));
    elements.resultsList.setAttribute("aria-busy", String(state.loading.results));
    elements.candidateDialog.setAttribute(
        "aria-busy",
        String(state.loading.candidate || state.loading.rescreen),
    );
}

function renderStatistics() {
    const totals = state.rankings
        .map((result) => Number(result?.scores?.total_score))
        .filter((score) => Number.isFinite(score));
    const strongMatches = state.rankings.filter((result) => (
        safeText(result.recommendation, "").toLowerCase() === "strong match"
    )).length;
    const average = totals.length > 0
        ? totals.reduce((sum, score) => sum + score, 0) / totals.length
        : 0;

    elements.totalJobs.textContent = String(state.jobs.length);
    elements.candidateStat.textContent = String(state.rankings.length);
    elements.strongMatchStat.textContent = String(strongMatches);
    elements.averageScoreStat.textContent = totals.length > 0
        ? average.toFixed(1)
        : "0";
}

function appendList(container, values, className = "plain-list", emptyText = "Not specified") {
    const items = valueAsList(values);
    if (items.length === 0) {
        container.appendChild(createElement("p", "", emptyText));
        return;
    }

    const list = createElement("ul", className);
    for (const value of items) {
        const itemClass = className === "chip-list" ? "chip" : "";
        list.appendChild(createElement("li", itemClass, value));
    }
    container.appendChild(list);
}

function addRequirementCard(container, title, values, options = {}) {
    const cardClasses = options.full
        ? "requirement-card summary-card"
        : "requirement-card";
    const card = createElement("article", cardClasses);
    card.appendChild(createElement("h3", "", title));

    if (options.text) {
        card.appendChild(createElement("p", "", safeText(values, "Not specified")));
    } else {
        appendList(card, values, options.chips ? "chip-list" : "plain-list", "Not specified");
    }

    container.appendChild(card);
}

function renderJobDetails() {
    const job = getSelectedJob();
    clearElement(elements.jobDetails);

    if (!job) {
        elements.selectedJobMeta.textContent = "No job selected";
        elements.uploadJobContext.textContent = "Select a job before adding resumes.";
        elements.jobDetails.className = "empty-state";
        elements.jobDetails.textContent = "Select a saved job to view its extracted requirements.";
        return;
    }

    const requirements = (
        job.structured_data
        && typeof job.structured_data === "object"
    )
        ? job.structured_data
        : (
            job.requirements
            && typeof job.requirements === "object"
                ? job.requirements
                : {}
        );

    elements.selectedJobMeta.textContent = (
        `Job #${job.id} · Created ${formatDate(job.created_at)}`
    );
    elements.uploadJobContext.textContent = `Screening for ${safeText(job.title, "selected job")}`;
    elements.jobDetails.className = "requirements-grid";

    addRequirementCard(
        elements.jobDetails,
        safeText(job.title, "Untitled job"),
        requirements.job_summary,
        { full: true, text: true },
    );
    addRequirementCard(
        elements.jobDetails,
        "Original description",
        job.description,
        { full: true, text: true },
    );
    addRequirementCard(elements.jobDetails, "Required skills", requirements.required_skills, { chips: true });
    addRequirementCard(elements.jobDetails, "Preferred skills", requirements.preferred_skills, { chips: true });
    addRequirementCard(elements.jobDetails, "Education", requirements.education_requirements);
    addRequirementCard(elements.jobDetails, "Experience", requirements.experience_requirements);
    addRequirementCard(elements.jobDetails, "Responsibilities", requirements.responsibilities);
    addRequirementCard(elements.jobDetails, "Keywords", requirements.keywords, { chips: true });
}

function renderJobs() {
    clearElement(elements.jobsList);
    const normalizedSearch = state.searchTerm.trim().toLowerCase();
    const filteredJobs = state.jobs.filter((job) => {
        if (!normalizedSearch) {
            return true;
        }
        return safeText(job.title, "").toLowerCase().includes(normalizedSearch)
            || String(job.id).includes(normalizedSearch);
    });

    if (state.jobs.length === 0) {
        elements.jobsList.className = "empty-state";
        elements.jobsList.textContent = "No jobs created yet. Use the form above to add the first position.";
        updateControlStates();
        return;
    }

    if (filteredJobs.length === 0) {
        elements.jobsList.className = "empty-state";
        elements.jobsList.textContent = "No saved jobs match this search.";
        updateControlStates();
        return;
    }

    elements.jobsList.className = "jobs-list";
    for (const job of filteredJobs) {
        const item = createElement("article", "job-list-item");
        if (job.id === state.selectedJobId) {
            item.classList.add("selected");
        }

        const selectButton = createElement("button", "job-select-button");
        selectButton.type = "button";
        selectButton.dataset.jobId = String(job.id);
        selectButton.dataset.action = "select-job";
        selectButton.setAttribute("aria-pressed", String(job.id === state.selectedJobId));
        selectButton.appendChild(createElement("strong", "", safeText(job.title, "Untitled job")));
        selectButton.appendChild(
            createElement("span", "", `Job #${job.id} · ${formatDate(job.created_at)}`),
        );

        const deleteButton = createElement("button", "job-delete-button", "Delete");
        deleteButton.type = "button";
        deleteButton.dataset.jobId = String(job.id);
        deleteButton.dataset.action = "delete-job";
        deleteButton.setAttribute(
            "aria-label",
            `Delete ${safeText(job.title, "job")}`,
        );

        item.append(selectButton, deleteButton);
        elements.jobsList.appendChild(item);
    }

    updateControlStates();
}

function resetSelectedJobState() {
    state.rankings = [];
    state.selectedFiles = [];
    state.selectedCandidate = null;
    state.requestIds.results += 1;
    state.requestIds.candidate += 1;
    elements.fileInput.value = "";
    clearElement(elements.screeningOutcome);
    setMessage(elements.uploadMessage);
    closeCandidateModal(false);
    renderFiles();
    renderResults();
    renderStatistics();
}

async function selectJob(jobId) {
    if (jobInteractionLocked() || jobId === state.selectedJobId) {
        return;
    }
    if (!state.jobs.some((job) => job.id === jobId)) {
        return;
    }

    state.selectedJobId = jobId;
    resetSelectedJobState();
    renderJobs();
    renderJobDetails();
    updateControlStates();
    await loadResults(jobId);
}

async function loadJobs(options = {}) {
    const requestId = ++state.requestIds.jobs;
    state.loading.jobs = true;
    setMessage(elements.jobsMessage, "Loading saved jobs...", "loading");
    updateControlStates();

    try {
        const jobs = await apiRequest("/api/jobs");
        if (!Array.isArray(jobs)) {
            throw new ApiError("The server returned an invalid jobs list.", 200);
        }
        if (requestId !== state.requestIds.jobs) {
            return;
        }

        state.jobs = jobs;
        if (Number.isInteger(options.selectedJobId)) {
            state.selectedJobId = options.selectedJobId;
        }

        const selectionExists = state.jobs.some((job) => job.id === state.selectedJobId);
        if (!selectionExists) {
            if (state.selectedJobId !== null) {
                resetSelectedJobState();
            }
            state.selectedJobId = null;
        }

        renderJobs();
        renderJobDetails();
        renderStatistics();
        setMessage(elements.jobsMessage);

        if (state.selectedJobId !== null) {
            await loadResults(state.selectedJobId);
        }
    } catch (error) {
        if (requestId === state.requestIds.jobs) {
            setMessage(elements.jobsMessage, errorText(error, "Unable to load saved jobs."), "error");
        }
    } finally {
        if (requestId === state.requestIds.jobs) {
            state.loading.jobs = false;
            updateControlStates();
        }
    }
}

function validateJobForm(title, description) {
    if (title.length < 2 || title.length > 200) {
        return {
            message: "Job title must contain between 2 and 200 characters.",
            field: elements.titleInput,
        };
    }
    if (description.length < 50 || description.length > 20000) {
        return {
            message: "Job description must contain between 50 and 20,000 characters.",
            field: elements.descriptionInput,
        };
    }
    return null;
}

async function createJob(event) {
    event.preventDefault();
    if (state.loading.createJob || jobInteractionLocked()) {
        return;
    }

    const title = elements.titleInput.value.trim();
    const description = elements.descriptionInput.value.trim();
    const validationError = validateJobForm(title, description);
    if (validationError) {
        setMessage(elements.formMessage, validationError.message, "error");
        validationError.field.focus();
        return;
    }

    state.loading.createJob = true;
    elements.createJobButton.textContent = "Extracting requirements...";
    setMessage(
        elements.formMessage,
        "The backend is extracting structured requirements. This may take a moment.",
        "loading",
    );
    updateControlStates();

    try {
        const createdJob = await apiRequest("/api/jobs", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ title, description }),
        });
        if (!createdJob || !Number.isInteger(createdJob.id)) {
            throw new ApiError("The server returned an invalid created-job response.", 200);
        }

        elements.jobForm.reset();
        elements.descriptionCount.textContent = "0 / 20,000";
        state.selectedJobId = createdJob.id;
        resetSelectedJobState();
        setMessage(elements.formMessage, "Job created and selected successfully.", "success");
        await loadJobs({ selectedJobId: createdJob.id });
    } catch (error) {
        setMessage(elements.formMessage, errorText(error, "Unable to create the job."), "error");
    } finally {
        state.loading.createJob = false;
        elements.createJobButton.textContent = "Extract and save job";
        updateControlStates();
    }
}

async function deleteJob(jobId) {
    if (jobInteractionLocked()) {
        return;
    }
    const job = state.jobs.find((item) => item.id === jobId);
    if (!job) {
        setMessage(elements.appMessage, "That job is no longer available.", "error");
        return;
    }

    const confirmed = window.confirm(
        `Delete “${safeText(job.title, "this job")}”? Linked screening results will also be deleted, and candidates with no remaining results may be removed.`,
    );
    if (!confirmed) {
        return;
    }

    state.loading.deleteJob = true;
    setMessage(elements.appMessage, "Deleting the job and linked results...", "loading");
    renderJobs();
    updateControlStates();

    try {
        const response = await apiRequest(`/api/jobs/${jobId}`, { method: "DELETE" });
        const deletedResults = Number(response?.deleted_results_count) || 0;
        const deletedCandidates = Number(response?.deleted_orphan_candidates_count) || 0;

        if (state.selectedJobId === jobId) {
            state.selectedJobId = null;
            resetSelectedJobState();
            renderJobDetails();
        }

        setMessage(
            elements.appMessage,
            `Job deleted. Removed ${deletedResults} screening result${deletedResults === 1 ? "" : "s"} and ${deletedCandidates} orphan candidate${deletedCandidates === 1 ? "" : "s"}.`,
            "success",
        );
        await loadJobs();
    } catch (error) {
        setMessage(elements.appMessage, errorText(error, "Unable to delete the job."), "error");
        if (error instanceof ApiError && error.status === 404) {
            await loadJobs();
        }
    } finally {
        state.loading.deleteJob = false;
        renderJobs();
        updateControlStates();
    }
}

function validateFile(file) {
    const filename = typeof file?.name === "string" ? file.name : "";
    const extension = filename.includes(".")
        ? filename.split(".").pop().toLowerCase()
        : "";

    if (!filename || !ALLOWED_EXTENSIONS.has(extension)) {
        return `${filename || "Unnamed file"}: only PDF and TXT files are supported.`;
    }
    if (file.size === 0) {
        return `${filename}: the file is empty.`;
    }
    if (file.size > MAX_FILE_SIZE) {
        return `${filename}: the file exceeds 5 MB.`;
    }
    return null;
}

function fileKey(file) {
    return `${file.name}:${file.size}:${file.lastModified}`;
}

function addFiles(fileList) {
    if (!getSelectedJob()) {
        setMessage(elements.uploadMessage, "Select a job before adding resumes.", "error");
        return;
    }
    if (state.loading.screening) {
        return;
    }

    const errors = [];
    const existingKeys = new Set(state.selectedFiles.map(fileKey));
    for (const file of Array.from(fileList || [])) {
        const validationError = validateFile(file);
        if (validationError) {
            errors.push(validationError);
            continue;
        }
        if (existingKeys.has(fileKey(file))) {
            errors.push(`${file.name}: this file is already selected.`);
            continue;
        }
        if (state.selectedFiles.length >= MAX_FILES) {
            errors.push(`A maximum of ${MAX_FILES} resumes can be screened at once.`);
            break;
        }
        state.selectedFiles.push(file);
        existingKeys.add(fileKey(file));
    }

    elements.fileInput.value = "";
    renderFiles();
    if (errors.length > 0) {
        setMessage(elements.uploadMessage, errors.join(" "), "error");
    } else if (state.selectedFiles.length > 0) {
        setMessage(
            elements.uploadMessage,
            `${state.selectedFiles.length} resume${state.selectedFiles.length === 1 ? "" : "s"} ready to screen.`,
            "success",
        );
    }
}

function renderFiles() {
    clearElement(elements.selectedFiles);
    for (const file of state.selectedFiles) {
        const item = createElement("article", "file-item");
        const details = createElement("div");
        details.appendChild(createElement("strong", "", safeText(file.name, "Unnamed file")));
        details.appendChild(createElement("span", "", formatFileSize(file.size)));

        const removeButton = createElement("button", "remove-file-button", "Remove");
        removeButton.type = "button";
        removeButton.dataset.fileKey = fileKey(file);
        removeButton.setAttribute("aria-label", `Remove ${safeText(file.name, "file")}`);
        item.append(details, removeButton);
        elements.selectedFiles.appendChild(item);
    }
    updateControlStates();
}

function removeFile(key) {
    if (state.loading.screening) {
        return;
    }
    state.selectedFiles = state.selectedFiles.filter((file) => fileKey(file) !== key);
    renderFiles();
    setMessage(
        elements.uploadMessage,
        state.selectedFiles.length > 0
            ? `${state.selectedFiles.length} resume${state.selectedFiles.length === 1 ? "" : "s"} ready to screen.`
            : "Selected files cleared.",
        state.selectedFiles.length > 0 ? "success" : "",
    );
}

function renderScreeningOutcome(response, fallbackFailures = []) {
    clearElement(elements.screeningOutcome);
    const successfulCount = Number(response?.successful_count) || 0;
    const failedFiles = Array.isArray(response?.failed_files)
        ? response.failed_files
        : fallbackFailures;
    const failedCount = Number(response?.failed_count) || failedFiles.length;

    if (successfulCount === 0 && failedCount === 0) {
        return;
    }

    elements.screeningOutcome.appendChild(createElement("h3", "", "Screening summary"));
    elements.screeningOutcome.appendChild(
        createElement(
            "p",
            "",
            `${successfulCount} successful · ${failedCount} failed`,
        ),
    );

    if (failedFiles.length > 0) {
        const list = createElement("ul", "failure-list");
        for (const failure of failedFiles) {
            const filename = safeText(failure?.filename, "Unknown file");
            const stage = safeText(failure?.stage, "processing");
            const message = safeText(failure?.error, "The file could not be processed.");
            list.appendChild(
                createElement("li", "failure-item", `${filename} · ${stage}: ${message}`),
            );
        }
        elements.screeningOutcome.appendChild(list);
    }
}

function failedFilesFromError(error) {
    const failures = error instanceof ApiError
        ? error.data?.detail?.failed_files
        : null;
    return Array.isArray(failures) ? failures : [];
}

async function screenSelectedResumes() {
    const selectedJob = getSelectedJob();
    if (!selectedJob) {
        setMessage(elements.uploadMessage, "Select a job before screening resumes.", "error");
        return;
    }
    if (state.selectedFiles.length === 0) {
        setMessage(elements.uploadMessage, "Choose at least one resume to screen.", "error");
        return;
    }
    if (state.loading.screening) {
        return;
    }

    const jobId = selectedJob.id;
    const submittedFiles = [...state.selectedFiles];
    const formData = new FormData();
    for (const file of submittedFiles) {
        formData.append("files", file);
    }

    state.loading.screening = true;
    elements.screenResumesButton.textContent = "Screening sequentially...";
    setMessage(
        elements.uploadMessage,
        "Resumes are being processed one at a time. Free-tier model requests may take several minutes.",
        "loading",
    );
    clearElement(elements.screeningOutcome);
    renderJobs();
    updateControlStates();

    try {
        const response = await apiRequest(`/api/jobs/${jobId}/screen`, {
            method: "POST",
            body: formData,
        });
        if (!response || typeof response !== "object") {
            throw new ApiError("The server returned an invalid screening response.", 200);
        }

        renderScreeningOutcome(response);
        const failedNames = new Set(
            (Array.isArray(response.failed_files) ? response.failed_files : [])
                .map((failure) => failure?.filename)
                .filter((name) => typeof name === "string"),
        );
        state.selectedFiles = submittedFiles.filter((file) => failedNames.has(file.name));
        renderFiles();

        setMessage(
            elements.uploadMessage,
            `${Number(response.successful_count) || 0} resume${Number(response.successful_count) === 1 ? "" : "s"} screened successfully.`,
            Number(response.failed_count) > 0 ? "warning" : "success",
        );

        if (state.selectedJobId === jobId) {
            await loadResults(jobId);
        }
    } catch (error) {
        const failures = failedFilesFromError(error);
        renderScreeningOutcome(
            { successful_count: 0, failed_count: failures.length, failed_files: failures },
            failures,
        );
        setMessage(elements.uploadMessage, errorText(error, "Unable to screen the selected resumes."), "error");
    } finally {
        state.loading.screening = false;
        elements.screenResumesButton.textContent = "Screen selected resumes";
        renderJobs();
        updateControlStates();
    }
}

function recommendationClass(value) {
    const normalized = safeText(value, "").toLowerCase();
    if (normalized.includes("strong")) {
        return "strong";
    }
    if (normalized.includes("good") || normalized.includes("potential")) {
        return "good";
    }
    if (normalized.includes("moderate")) {
        return "moderate";
    }
    if (
        normalized.includes("weak")
        || normalized.includes("not recommended")
    ) {
        return "weak";
    }
    return "";
}

function addScoreItem(container, label, value, maximum, isTotal = false) {
    const card = createElement("div", isTotal ? "score-item total-score" : "score-item");
    card.appendChild(createElement("span", "", label));
    const numericValue = Number(value);
    card.appendChild(
        createElement(
            "strong",
            "",
            `${Number.isFinite(numericValue) ? numericValue : 0} / ${maximum}`,
        ),
    );
    container.appendChild(card);
}

function appendResultSection(container, title, values, options = {}) {
    const section = createElement("section", "result-section");
    section.appendChild(createElement("h4", "", title));
    if (options.text) {
        section.appendChild(createElement("p", "", safeText(values, "Not available")));
    } else {
        appendList(section, values, "chip-list", "Not available");
        if (options.missing) {
            for (const chip of section.querySelectorAll(".chip")) {
                chip.classList.add("missing");
            }
        }
    }
    container.appendChild(section);
}

function renderResults() {
    clearElement(elements.resultsList);
    const selectedJob = getSelectedJob();
    elements.candidateCount.textContent = `${state.rankings.length} candidate${state.rankings.length === 1 ? "" : "s"}`;
    elements.resultsJobTitle.textContent = selectedJob
        ? safeText(selectedJob.title, "Selected job")
        : "No job selected";

    if (!selectedJob) {
        elements.resultsList.className = "empty-state";
        elements.resultsList.textContent = "Select a job to load ranked candidates.";
        renderStatistics();
        updateControlStates();
        return;
    }

    if (state.rankings.length === 0) {
        elements.resultsList.className = "empty-state";
        elements.resultsList.textContent = "No candidates have been screened for this job yet.";
        renderStatistics();
        updateControlStates();
        return;
    }

    elements.resultsList.className = "results-list";
    for (const result of state.rankings) {
        const card = createElement("article", "result-card");
        const topLine = createElement("div", "result-topline");
        const candidateHeading = createElement("div", "candidate-heading");
        candidateHeading.appendChild(
            createElement("span", "rank-badge", `#${Number(result.rank) || "–"}`),
        );
        const headingText = createElement("div");
        headingText.appendChild(
            createElement("h3", "", safeText(result.candidate_name, "Unknown candidate")),
        );
        headingText.appendChild(
            createElement("p", "", safeText(result.resume_filename, "Filename unavailable")),
        );
        candidateHeading.appendChild(headingText);

        const recommendation = safeText(result.recommendation, "Recommendation unavailable");
        const badge = createElement(
            "span",
            `recommendation-badge ${recommendationClass(recommendation)}`.trim(),
            recommendation,
        );
        topLine.append(candidateHeading, badge);
        card.appendChild(topLine);

        const scores = result.scores && typeof result.scores === "object" ? result.scores : {};
        const scoreGrid = createElement("div", "score-grid");
        addScoreItem(scoreGrid, "Total", scores.total_score, 100, true);
        addScoreItem(scoreGrid, "Required", scores.required_skills_score, 30);
        addScoreItem(scoreGrid, "Preferred", scores.preferred_skills_score, 10);
        addScoreItem(scoreGrid, "Experience", scores.experience_score, 25);
        addScoreItem(scoreGrid, "Education", scores.education_score, 15);
        addScoreItem(scoreGrid, "Projects", scores.project_relevance_score, 20);
        card.appendChild(scoreGrid);

        const detailsGrid = createElement("div", "result-details-grid");
        appendResultSection(detailsGrid, "Matched skills", result.matched_skills);
        appendResultSection(detailsGrid, "Missing required", result.missing_required_skills, { missing: true });
        appendResultSection(detailsGrid, "Evidence", result.evidence);
        card.appendChild(detailsGrid);

        const justification = createElement("div", "result-section justification-block");
        justification.appendChild(createElement("h4", "", "Justification"));
        justification.appendChild(
            createElement("p", "", safeText(result.justification, "Not available")),
        );
        card.appendChild(justification);

        const actions = createElement("div", "result-actions");
        const detailsButton = createElement("button", "secondary-button compact-button", "View candidate details");
        detailsButton.type = "button";
        detailsButton.dataset.resultId = String(result.screening_result_id);
        detailsButton.dataset.action = "open-candidate";
        detailsButton.setAttribute(
            "aria-label",
            `View details for ${safeText(result.candidate_name, "candidate")}`,
        );
        actions.appendChild(detailsButton);
        card.appendChild(actions);
        elements.resultsList.appendChild(card);
    }

    renderStatistics();
    updateControlStates();
}

async function loadResults(jobId = state.selectedJobId) {
    if (!Number.isInteger(jobId)) {
        state.rankings = [];
        renderResults();
        return;
    }

    const requestId = ++state.requestIds.results;
    state.loading.results = true;
    setMessage(elements.resultsMessage, "Loading ranked candidates...", "loading");
    updateControlStates();

    try {
        const response = await apiRequest(`/api/jobs/${jobId}/results`);
        if (!response || !Array.isArray(response.results)) {
            throw new ApiError("The server returned invalid ranked results.", 200);
        }
        if (
            requestId !== state.requestIds.results
            || state.selectedJobId !== jobId
        ) {
            return;
        }

        state.rankings = response.results;
        renderResults();
        setMessage(elements.resultsMessage);
    } catch (error) {
        if (
            requestId === state.requestIds.results
            && state.selectedJobId === jobId
        ) {
            state.rankings = [];
            renderResults();
            setMessage(elements.resultsMessage, errorText(error, "Unable to load ranked results."), "error");
        }
    } finally {
        if (requestId === state.requestIds.results) {
            state.loading.results = false;
            updateControlStates();
        }
    }
}

function addOverviewItem(container, label, value) {
    const item = createElement("div", "overview-item");
    item.appendChild(createElement("span", "", label));
    item.appendChild(createElement("strong", "", safeText(value, "Not available")));
    container.appendChild(item);
}

function addDetailCard(container, title, value, options = {}) {
    const card = createElement(
        "article",
        options.full ? "detail-card full-detail-card" : "detail-card",
    );
    card.appendChild(createElement("h3", "", title));
    if (options.list) {
        appendList(card, value, options.chips ? "chip-list" : "plain-list", "Not available");
        if (options.missing) {
            for (const chip of card.querySelectorAll(".chip")) {
                chip.classList.add("missing");
            }
        }
    } else {
        card.appendChild(createElement("p", "", safeText(value, "Not available")));
    }
    container.appendChild(card);
}

function renderCandidateDetail() {
    clearElement(elements.candidateDetailContent);
    const detail = state.selectedCandidate;
    if (!detail) {
        elements.candidateDialogTitle.textContent = "Candidate details";
        elements.candidateDetailContent.className = "empty-state";
        elements.candidateDetailContent.textContent = state.loading.candidate
            ? "Loading candidate details..."
            : "Candidate details are unavailable.";
        updateControlStates();
        return;
    }

    elements.candidateDetailContent.className = "candidate-detail-content";
    const candidate = detail.candidate && typeof detail.candidate === "object"
        ? detail.candidate
        : {};
    const structured = candidate.structured_data && typeof candidate.structured_data === "object"
        ? candidate.structured_data
        : {};
    const scores = detail.scores && typeof detail.scores === "object" ? detail.scores : {};

    elements.candidateDialogTitle.textContent = safeText(candidate.name, "Candidate details");
    const overview = createElement("div", "candidate-overview");
    addOverviewItem(overview, "Email", candidate.email);
    addOverviewItem(overview, "Phone", candidate.phone);
    addOverviewItem(overview, "Resume", candidate.resume_filename);
    addOverviewItem(overview, "Screened", formatDate(detail.screened_at));
    elements.candidateDetailContent.appendChild(overview);

    const scoreGrid = createElement("div", "score-grid");
    addScoreItem(scoreGrid, "Total", scores.total_score, 100, true);
    addScoreItem(scoreGrid, "Required", scores.required_skills_score, 30);
    addScoreItem(scoreGrid, "Preferred", scores.preferred_skills_score, 10);
    addScoreItem(scoreGrid, "Experience", scores.experience_score, 25);
    addScoreItem(scoreGrid, "Education", scores.education_score, 15);
    addScoreItem(scoreGrid, "Projects", scores.project_relevance_score, 20);
    elements.candidateDetailContent.appendChild(scoreGrid);

    const grid = createElement("div", "candidate-detail-grid");
    addDetailCard(grid, "Recommendation", detail.recommendation);
    addDetailCard(grid, "Extracted skills", structured.skills, { list: true, chips: true });
    addDetailCard(grid, "Education", structured.education);
    addDetailCard(grid, "Experience", structured.experience);
    addDetailCard(grid, "Projects", structured.projects);
    addDetailCard(grid, "Certifications", structured.certifications);
    addDetailCard(grid, "Matched skills", detail.matched_skills, { list: true, chips: true });
    addDetailCard(grid, "Missing required skills", detail.missing_required_skills, {
        list: true,
        chips: true,
        missing: true,
    });
    addDetailCard(grid, "Evidence", detail.evidence, { list: true, full: true });
    addDetailCard(grid, "Justification", detail.justification, { full: true });
    elements.candidateDetailContent.appendChild(grid);
    updateControlStates();
}

function openModal(triggerElement) {
    state.lastFocusedElement = triggerElement || document.activeElement;
    elements.candidateModal.hidden = false;
    document.body.classList.add("modal-open");
    elements.candidateDialog.focus();
}

function closeCandidateModal(restoreFocus = true) {
    if (elements.candidateModal.hidden) {
        return;
    }
    state.requestIds.candidate += 1;
    elements.candidateModal.hidden = true;
    document.body.classList.remove("modal-open");
    setMessage(elements.candidateMessage);
    if (
        restoreFocus
        && state.lastFocusedElement
        && typeof state.lastFocusedElement.focus === "function"
        && document.contains(state.lastFocusedElement)
    ) {
        state.lastFocusedElement.focus();
    }
    state.lastFocusedElement = null;
}

async function openCandidateDetails(resultId, triggerElement) {
    if (!Number.isInteger(resultId)) {
        return;
    }
    const requestId = ++state.requestIds.candidate;
    state.loading.candidate = true;
    state.selectedCandidate = null;
    openModal(triggerElement);
    setMessage(elements.candidateMessage, "Loading candidate details...", "loading");
    renderCandidateDetail();

    try {
        const detail = await apiRequest(`/api/screening-results/${resultId}`);
        if (!detail || typeof detail !== "object" || !detail.candidate) {
            throw new ApiError("The server returned invalid candidate details.", 200);
        }
        if (requestId !== state.requestIds.candidate || elements.candidateModal.hidden) {
            return;
        }
        state.selectedCandidate = detail;
        renderCandidateDetail();
        setMessage(elements.candidateMessage);
    } catch (error) {
        if (requestId === state.requestIds.candidate) {
            renderCandidateDetail();
            setMessage(elements.candidateMessage, errorText(error, "Unable to load candidate details."), "error");
        }
    } finally {
        if (requestId === state.requestIds.candidate) {
            state.loading.candidate = false;
            updateControlStates();
        }
    }
}

async function rescreenCandidate() {
    const previousDetail = state.selectedCandidate;
    const resultId = previousDetail?.screening_result_id;
    if (!Number.isInteger(resultId) || state.loading.rescreen) {
        return;
    }
    const confirmed = window.confirm(
        "Re-screen this candidate? This sends another anonymized assessment request and updates the existing result.",
    );
    if (!confirmed) {
        return;
    }

    state.loading.rescreen = true;
    elements.rescreenCandidateButton.textContent = "Re-screening...";
    setMessage(elements.candidateMessage, "Re-screening the candidate. The current result will remain if this fails.", "loading");
    updateControlStates();

    try {
        const updated = await apiRequest(`/api/screening-results/${resultId}/rescreen`, {
            method: "POST",
        });
        if (!updated || typeof updated !== "object" || !updated.candidate) {
            throw new ApiError("The server returned invalid updated candidate details.", 200);
        }
        state.selectedCandidate = updated;
        renderCandidateDetail();
        setMessage(elements.candidateMessage, "Candidate re-screened successfully.", "success");
        if (Number.isInteger(state.selectedJobId)) {
            await loadResults(state.selectedJobId);
        }
    } catch (error) {
        state.selectedCandidate = previousDetail;
        renderCandidateDetail();
        setMessage(elements.candidateMessage, errorText(error, "Unable to re-screen the candidate."), "error");
    } finally {
        state.loading.rescreen = false;
        elements.rescreenCandidateButton.textContent = "Re-screen candidate";
        updateControlStates();
    }
}

async function deleteCandidate() {
    const detail = state.selectedCandidate;
    const candidateId = detail?.candidate?.id;
    if (!Number.isInteger(candidateId) || state.loading.deleteCandidate) {
        return;
    }
    const candidateName = safeText(detail.candidate.name, "this candidate");
    const confirmed = window.confirm(
        `Delete ${candidateName}? All screening results linked to this candidate will also be deleted.`,
    );
    if (!confirmed) {
        return;
    }

    state.loading.deleteCandidate = true;
    elements.deleteCandidateButton.textContent = "Deleting...";
    setMessage(elements.candidateMessage, "Deleting the candidate and linked results...", "loading");
    updateControlStates();

    try {
        const response = await apiRequest(`/api/candidates/${candidateId}`, {
            method: "DELETE",
        });
        const deletedResults = Number(response?.deleted_results_count) || 0;
        closeCandidateModal(false);
        state.selectedCandidate = null;
        setMessage(
            elements.appMessage,
            `Candidate deleted with ${deletedResults} linked screening result${deletedResults === 1 ? "" : "s"}.`,
            "success",
        );
        if (Number.isInteger(state.selectedJobId)) {
            await loadResults(state.selectedJobId);
        }
    } catch (error) {
        setMessage(elements.candidateMessage, errorText(error, "Unable to delete the candidate."), "error");
        if (error instanceof ApiError && error.status === 404) {
            if (Number.isInteger(state.selectedJobId)) {
                await loadResults(state.selectedJobId);
            }
        }
    } finally {
        state.loading.deleteCandidate = false;
        elements.deleteCandidateButton.textContent = "Delete candidate";
        updateControlStates();
    }
}

function trapModalFocus(event) {
    if (elements.candidateModal.hidden || event.key !== "Tab") {
        return;
    }
    const focusable = Array.from(
        elements.candidateDialog.querySelectorAll(
            "button:not([disabled]), a[href], input:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex='-1'])",
        ),
    ).filter((element) => !element.hidden);
    if (focusable.length === 0) {
        event.preventDefault();
        elements.candidateDialog.focus();
        return;
    }
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
    }
}

elements.jobForm.addEventListener("submit", createJob);
elements.descriptionInput.addEventListener("input", () => {
    elements.descriptionCount.textContent = `${elements.descriptionInput.value.length.toLocaleString()} / 20,000`;
});
elements.jobSearch.addEventListener("input", () => {
    state.searchTerm = elements.jobSearch.value;
    renderJobs();
});
elements.refreshJobsButton.addEventListener("click", () => loadJobs());
elements.deleteJobButton.addEventListener("click", () => {
    if (Number.isInteger(state.selectedJobId)) {
        deleteJob(state.selectedJobId);
    }
});

elements.jobsList.addEventListener("click", (event) => {
    const button = event.target.closest("button[data-action]");
    if (!button) {
        return;
    }
    const jobId = Number(button.dataset.jobId);
    if (!Number.isInteger(jobId)) {
        return;
    }
    if (button.dataset.action === "select-job") {
        selectJob(jobId);
    } else if (button.dataset.action === "delete-job") {
        deleteJob(jobId);
    }
});

elements.fileInput.addEventListener("change", () => addFiles(elements.fileInput.files));
for (const eventName of ["dragenter", "dragover"]) {
    elements.dropZone.addEventListener(eventName, (event) => {
        event.preventDefault();
        if (!elements.fileInput.disabled) {
            elements.dropZone.classList.add("drag-active");
        }
    });
}
for (const eventName of ["dragleave", "drop"]) {
    elements.dropZone.addEventListener(eventName, (event) => {
        event.preventDefault();
        elements.dropZone.classList.remove("drag-active");
    });
}
elements.dropZone.addEventListener("drop", (event) => {
    if (!elements.fileInput.disabled) {
        addFiles(event.dataTransfer?.files);
    }
});
elements.clearFilesButton.addEventListener("click", () => {
    if (!state.loading.screening) {
        state.selectedFiles = [];
        elements.fileInput.value = "";
        renderFiles();
        setMessage(elements.uploadMessage, "Selected files cleared.");
    }
});
elements.selectedFiles.addEventListener("click", (event) => {
    const button = event.target.closest("button[data-file-key]");
    if (button) {
        removeFile(button.dataset.fileKey);
    }
});
elements.screenResumesButton.addEventListener("click", screenSelectedResumes);

elements.refreshResultsButton.addEventListener("click", () => {
    if (Number.isInteger(state.selectedJobId)) {
        loadResults(state.selectedJobId);
    }
});
elements.resultsList.addEventListener("click", (event) => {
    const button = event.target.closest("button[data-action='open-candidate']");
    if (!button) {
        return;
    }
    const resultId = Number(button.dataset.resultId);
    openCandidateDetails(resultId, button);
});

elements.closeCandidateButton.addEventListener("click", () => closeCandidateModal());
elements.candidateModal.addEventListener("click", (event) => {
    if (event.target === elements.candidateModal) {
        closeCandidateModal();
    }
});
elements.rescreenCandidateButton.addEventListener("click", rescreenCandidate);
elements.deleteCandidateButton.addEventListener("click", deleteCandidate);
document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !elements.candidateModal.hidden) {
        closeCandidateModal();
        return;
    }
    trapModalFocus(event);
});

renderJobDetails();
renderFiles();
renderResults();
renderStatistics();
updateControlStates();
loadJobs();
