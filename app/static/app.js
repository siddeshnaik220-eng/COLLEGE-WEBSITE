const app = document.getElementById("app");
const toast = document.getElementById("toast");
let csrfToken = "";
let currentUser = null;
let currentPage = "overview";
const maxUploadMb = Number(app.dataset.maxUploadMb || 20);
let toastTimer;

const icons = { overview: "▦", assignments: "▤", submissions: "⇧", users: "♙", academics: "⌂", notifications: "◉", reports: "▥" };
const titles = { overview: "Overview", assignments: "Assignments", submissions: "Submissions", users: "User management", academics: "Academic setup", notifications: "Notifications", reports: "Reports" };

function esc(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[char]));
}

function showToast(message, isError = false) {
  toast.textContent = message;
  toast.className = `toast show${isError ? " error" : ""}`;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { toast.className = "toast"; }, 3200);
}

async function request(path, options = {}) {
  const headers = new Headers(options.headers || {});
  headers.set("Accept", "application/json");
  if (options.body && !(options.body instanceof FormData)) headers.set("Content-Type", "application/json");
  if (["POST", "PUT", "PATCH", "DELETE"].includes((options.method || "GET").toUpperCase())) {
    headers.set("X-CSRF-Token", csrfToken);
  }
  const response = await fetch(`/api/v1${path}`, { ...options, headers, credentials: "same-origin" });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(body?.error?.message || `Request failed (${response.status}).`);
  }
  if (response.headers.get("content-type")?.includes("application/json")) {
    const body = await response.json();
    return body.data;
  }
  return response;
}

function fmtDate(value, includeTime = false) {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "—" : date.toLocaleString(undefined, {
    month: "short", day: "numeric", year: "numeric",
    ...(includeTime ? { hour: "numeric", minute: "2-digit" } : {}),
  });
}

function fmtStatus(value) {
  return `<span class="badge ${esc(value)}">${esc(value)}</span>`;
}

function statCard(label, value, note = "") {
  return `<article class="stat-card"><span class="stat-label">${esc(label)}</span><strong class="stat-value">${esc(value)}</strong><div class="stat-note">${esc(note)}</div></article>`;
}

function heading(title, description, action = "") {
  return `<div class="page-heading"><div><h1>${esc(title)}</h1><p>${esc(description)}</p></div>${action}</div>`;
}

function table(headers, rows, emptyText = "Nothing to show yet.") {
  if (!rows.length) return `<div class="empty">${esc(emptyText)}</div>`;
  return `<div class="table-wrap"><table><thead><tr>${headers.map((header) => `<th>${header}</th>`).join("")}</tr></thead><tbody>${rows.join("")}</tbody></table></div>`;
}

function loginView(error = "") {
  app.innerHTML = `<section class="login-wrap">
    <div class="login-card">
      <div class="login-heading"><div class="brand-mark">B</div><span class="eyebrow">BMSIT College</span><h1>Assignment Management System</h1><p>One place for assignments, submissions and feedback.</p></div>
      <form id="login-form">
        <div class="field"><label for="login-id">USN, Faculty ID or college email</label><input id="login-id" name="login_id" autocomplete="username" required placeholder="Enter your login ID"></div>
        <div class="field"><label for="password">Password</label><input id="password" name="password" type="password" autocomplete="current-password" required placeholder="Enter your password"></div>
        <p class="login-error">${esc(error)}</p>
        <button class="btn btn-block" type="submit">Sign in</button>
      </form>
      <div class="demo-box"><strong>Demo accounts <span class="muted">(password: Demo123!)</span></strong><div class="demo-accounts">
        ${[["Administrator", "admin"], ["Professor", "faculty001"], ["Student", "1BM23CS001"]].map(([label, id]) => `<div class="demo-account"><span>${label}</span><button type="button" data-demo="${id}">${id} · Use demo</button></div>`).join("")}
      </div></div>
    </div>
  </section>`;
  document.querySelectorAll("[data-demo]").forEach((button) => button.addEventListener("click", () => {
    document.getElementById("login-id").value = button.dataset.demo;
    document.getElementById("password").value = "Demo123!";
    document.getElementById("password").focus();
  }));
  document.getElementById("login-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    try {
      const data = await request("/auth/login", { method: "POST", body: JSON.stringify(Object.fromEntries(form)) });
      csrfToken = data.csrf_token;
      currentUser = data.user;
      currentPage = "overview";
      await renderShell();
    } catch (error) {
      loginView(error.message);
    }
  });
}

function navItems() {
  if (currentUser.role === "student") return [["overview", "Overview"], ["assignments", "Assignments"], ["submissions", "My submissions"], ["notifications", "Notifications"]];
  if (currentUser.role === "professor") return [["overview", "Overview"], ["assignments", "My assignments"], ["notifications", "Notifications"]];
  return [["overview", "Overview"], ["users", "Users"], ["academics", "Academic setup"], ["reports", "Reports"], ["notifications", "Notifications"]];
}

async function renderShell() {
  app.innerHTML = `<div class="shell">
    <aside class="sidebar" id="sidebar"><div class="brand"><div class="brand-mark">B</div><div class="brand-name">BMSIT AMS<small>Academic workspace</small></div></div>
      <div class="nav-label">Workspace</div><nav class="nav-list">${navItems().map(([key, label]) => `<button class="nav-item ${key === currentPage ? "active" : ""}" data-page="${key}"><span class="nav-icon">${icons[key]}</span>${label}</button>`).join("")}</nav>
      <div class="sidebar-bottom">Assignment Management System<br>Computer Science & Engineering</div></aside>
    <section class="main-area"><header class="topbar"><div style="display:flex;align-items:center;gap:12px"><button class="mobile-menu" id="menu-button" aria-label="Open navigation">☰</button><span class="topbar-title">BMSIT College&nbsp; / &nbsp;${esc(titles[currentPage])}</span></div>
      <div class="user-chip"><div class="avatar">${esc(currentUser.full_name.split(/\s+/).map((part) => part[0]).slice(0, 2).join("").toUpperCase())}</div><div class="user-copy"><strong>${esc(currentUser.full_name)}</strong><span>${esc(currentUser.role)}</span></div><button class="btn btn-secondary btn-small" id="logout-button">Sign out</button></div></header>
      <main class="content" id="page-content"><div class="loading-screen">Loading your workspace…</div></main></section></div>`;
  document.querySelectorAll("[data-page]").forEach((button) => button.addEventListener("click", () => {
    currentPage = button.dataset.page;
    renderShell();
  }));
  document.getElementById("menu-button").addEventListener("click", () => document.getElementById("sidebar").classList.toggle("open"));
  document.getElementById("logout-button").addEventListener("click", async () => {
    try { await request("/auth/logout", { method: "POST", body: "{}" }); } catch (error) { showToast(error.message, true); }
    currentUser = null;
    try {
      csrfToken = (await request("/auth/csrf")).csrf_token;
    } catch (error) {
      showToast(error.message, true);
    }
    loginView();
  });
  try {
    await renderPage();
  } catch (error) {
    document.getElementById("page-content").innerHTML = `<div class="page-error">${esc(error.message)}</div>`;
  }
}

async function renderPage() {
  const area = document.getElementById("page-content");
  if (currentPage === "overview") return renderOverview(area);
  if (currentPage === "assignments") return currentUser.role === "student" ? renderStudentAssignments(area) : renderProfessorAssignments(area);
  if (currentPage === "submissions") return renderStudentSubmissions(area);
  if (currentPage === "users") return renderUsers(area);
  if (currentPage === "academics") return renderAcademics(area);
  if (currentPage === "notifications") return renderNotifications(area);
  if (currentPage === "reports") return renderReports(area);
}

async function renderOverview(area) {
  if (currentUser.role === "student") {
    const data = await request("/student/dashboard");
    const count = data.counts;
    area.innerHTML = `${heading("Good to see you, " + currentUser.full_name.split(" ")[0], "Here’s what’s happening with your coursework.")}
      <section class="cards">${statCard("Total assignments", count.total, "In your semester")}${statCard("Pending", count.pending, "Ready for your work")}${statCard("Submitted", count.submitted, "Awaiting feedback")}${statCard("Evaluated", count.evaluated, "Results published")}</section>
      <section class="panel"><div class="panel-heading"><div><h2>Upcoming assignments</h2><p>Published work for your academic group</p></div><button class="btn btn-secondary btn-small" data-page="assignments">View all</button></div>
        ${table(["Assignment", "Subject", "Due date", "Status"], data.upcoming.map((item) => `<tr><td><span class="primary-cell">${esc(item.title)}</span><span class="secondary-cell">${esc(item.description)}</span></td><td>${esc(item.subject)}</td><td>${fmtDate(item.due_at)}</td><td>${fmtStatus(item.submission?.status || "Pending")}</td></tr>`), "No published assignments yet.")}</section>
      <section class="panel"><div class="panel-heading"><div><h2>Recent submissions</h2><p>Your latest uploaded work and published results</p></div></div>
        ${table(["Assignment", "Submitted", "Status", "Result"], data.recent_submissions.map((item) => `<tr><td>${esc(item.assignment)}</td><td>${fmtDate(item.submitted_at, true)}</td><td>${fmtStatus(item.status)}</td><td>${item.evaluation ? `${esc(item.evaluation.marks)} marks · ${esc(item.evaluation.feedback || "No written feedback")}` : "Not published"}</td></tr>`), "Your submission history will appear here.")}</section>`;
  } else if (currentUser.role === "professor") {
    const data = await request("/professor/dashboard");
    area.innerHTML = `${heading("Teaching overview", "Monitor assignments, student work and evaluation progress.", `<button class="btn" data-action="new-assignment">＋ New assignment</button>`)}
      <section class="cards">${statCard("Assignments", data.counts.assignments, "Created by you")}${statCard("Submissions", data.counts.submissions, "Across your assignments")}${statCard("To evaluate", data.counts.to_evaluate, "Awaiting published feedback")}${statCard("Completion", `${data.counts.completion_percent}%`, "Submitted / expected")}</section>
      <section class="panel"><div class="panel-heading"><div><h2>My assignments</h2><p>Current work in your assigned subject areas</p></div><button class="btn btn-secondary btn-small" data-page="assignments">Manage</button></div>
        ${table(["Assignment", "Subject", "Due date", "State", "Action"], data.assignments.slice(0, 6).map((item) => `<tr><td><span class="primary-cell">${esc(item.title)}</span></td><td>${esc(item.subject)}</td><td>${fmtDate(item.due_at)}</td><td>${fmtStatus(item.status)}</td><td><button class="btn btn-secondary btn-small" data-action="view-submissions" data-id="${item.id}">Review</button></td></tr>`), "Create your first assignment to get started.")}</section>
      <section class="panel"><div class="panel-heading"><div><h2>Recent submissions</h2><p>Latest activity from your students</p></div></div>
        ${table(["Student", "Assignment", "Submitted", "Status"], data.recent_submissions.map((item) => `<tr><td>${esc(item.student)}</td><td>${esc(item.assignment)}</td><td>${fmtDate(item.submitted_at, true)}</td><td>${fmtStatus(item.status)} ${item.is_late ? '<span class="badge Overdue">Late</span>' : ""}</td></tr>`), "No submissions received yet.")}</section>`;
    attachProfessorActions(area);
  } else {
    const data = await request("/admin/dashboard");
    area.innerHTML = `${heading("College overview", "A summary of assignment activity and academic operations.")}
      <section class="cards">${statCard("Students", data.counts.students, "Registered accounts")}${statCard("Professors", data.counts.professors, "Teaching staff")}${statCard("Departments", data.counts.departments, "Active departments")}${statCard("Assignments", data.counts.assignments, `${data.counts.submissions} submissions`)}</section>
      <section class="panel"><div class="panel-heading"><div><h2>Recent activity</h2><p>Important changes across the system</p></div></div>
        ${table(["Activity", "By", "Type", "When"], data.activity.map((item) => `<tr><td>${esc(item.action.replaceAll(".", " "))}</td><td>${esc(item.actor)}</td><td>${esc(item.entity_type)}</td><td>${fmtDate(item.created_at, true)}</td></tr>`), "System activity will appear here.")}</section>
      <div class="notice">Use the Users and Academic setup pages to configure your department, semesters, subjects and accounts.</div>`;
  }
}

async function renderStudentAssignments(area) {
  const assignments = await request("/student/assignments");
  area.innerHTML = `${heading("Assignments", "Browse work assigned to your department and semester.")}
    <section class="panel"><div class="filters"><input class="search-input" id="assignment-search" placeholder="Search title or instructions"><span class="muted">${assignments.length} assignments</span></div><div id="assignment-table"></div></section>`;
  const draw = (search = "") => {
    const filtered = assignments.filter((item) => `${item.title} ${item.description} ${item.subject}`.toLowerCase().includes(search.toLowerCase()));
    document.getElementById("assignment-table").innerHTML = table(["Assignment", "Subject", "Due date", "Status", "Work"], filtered.map((item) => {
      const status = item.derived_status;
      const submit = item.submission ? `<a class="btn btn-secondary btn-small" href="/api/v1/files/submissions/${item.submission.id}" data-download>Download</a>${item.allow_resubmission ? ` <button class="btn btn-secondary btn-small" data-action="submit" data-id="${item.id}">Resubmit</button>` : ""}` : `<button class="btn btn-small" data-action="submit" data-id="${item.id}">Upload work</button>`;
      return `<tr><td><span class="primary-cell">${esc(item.title)}</span><span class="secondary-cell">${esc(item.description)}</span>${item.reference_name ? `<span class="secondary-cell"><a href="/api/v1/files/references/${item.id}" data-download>Reference: ${esc(item.reference_name)}</a></span>` : ""}</td><td>${esc(item.subject)}<span class="secondary-cell">${esc(item.subject_code)}</span></td><td>${fmtDate(item.due_at, true)}</td><td>${fmtStatus(status)}${item.submission?.is_late ? '<span class="badge Overdue">Late</span>' : ""}</td><td>${submit}</td></tr>`;
    }), "No matching assignments.");
  };
  draw();
  document.getElementById("assignment-search").addEventListener("input", (event) => draw(event.target.value));
  area.querySelectorAll("[data-action='submit']").forEach((button) => button.addEventListener("click", () => openUpload(button.dataset.id, assignments.find((item) => String(item.id) === button.dataset.id))));
}

function openUpload(id, assignment) {
  const area = document.getElementById("page-content");
  const existing = document.getElementById("upload-panel");
  if (existing) existing.remove();
  const panel = document.createElement("section");
  panel.id = "upload-panel";
  panel.className = "panel";
  panel.innerHTML = `<div class="panel-heading"><div><h2>Submit: ${esc(assignment.title)}</h2><p>PDF or DOCX · Maximum ${maxUploadMb} MB${assignment.allow_late ? " · Late submissions accepted" : ""}</p></div><button class="btn btn-secondary btn-small" data-action="close-upload">Close</button></div>
    <form id="upload-form"><div class="field"><label for="submission-file">Select your completed assignment</label><input id="submission-file" type="file" name="file" accept=".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document" required></div><button class="btn" type="submit">Upload submission</button></form>`;
  area.prepend(panel);
  panel.querySelector("[data-action='close-upload']").addEventListener("click", () => panel.remove());
  panel.querySelector("form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const button = event.currentTarget.querySelector("button[type='submit']");
    button.disabled = true;
    try {
      const formData = new FormData(event.currentTarget);
      const data = await request(`/student/assignments/${id}/submissions`, { method: "POST", body: formData });
      showToast(`Submission received (attempt ${data.attempt}).`);
      await renderStudentAssignments(area);
    } catch (error) {
      showToast(error.message, true);
      button.disabled = false;
    }
  });
}

async function renderStudentSubmissions(area) {
  const data = await request("/student/submissions");
  area.innerHTML = `${heading("My submissions", "Track submitted files and review results once they are published.")}
    <section class="panel">    ${table(["Assignment", "File", "Submitted", "Status", "Marks / feedback"], data.map((item) => `<tr><td>${esc(item.assignment)}<span class="secondary-cell">Attempt ${item.attempt}</span></td><td><a href="/api/v1/files/submissions/${item.id}" data-download>${esc(item.file_name)}</a></td><td>${fmtDate(item.submitted_at, true)}${item.is_late ? '<span class="badge Overdue">Late</span>' : ""}</td><td>${fmtStatus(item.status)}</td><td>${item.evaluation ? `<strong>${esc(item.evaluation.marks)} / ${esc(item.max_marks)}</strong><span class="secondary-cell">${esc(item.evaluation.feedback || "No written feedback")}</span>` : "Not published"}</td></tr>`), "No submissions yet.")}</section>`;
}

async function renderProfessorAssignments(area) {
  const assignments = await request("/professor/assignments");
  const ownSubjects = await request("/professor/subjects");
  area.innerHTML = `${heading("My assignments", "Create, publish and manage coursework for your assigned subjects.", `<button class="btn" data-action="new-assignment">＋ New assignment</button>`)}
    <section class="panel">${table(["Assignment", "Subject / semester", "Due date", "Status", "Actions"], assignments.map((item) => `<tr><td><span class="primary-cell">${esc(item.title)}</span><span class="secondary-cell">${esc(item.description)}</span></td><td>${esc(item.subject)}<span class="secondary-cell">Semester ${esc(item.semester)} · ${esc(item.department)}</span></td><td>${fmtDate(item.due_at, true)}</td><td>${fmtStatus(item.status)}</td><td><button class="btn btn-secondary btn-small" data-action="view-submissions" data-id="${item.id}">Submissions</button> <button class="btn btn-secondary btn-small" data-action="edit-assignment" data-id="${item.id}">Edit</button>${item.status === "Published" ? ` <button class="btn btn-danger btn-small" data-action="change-state" data-id="${item.id}" data-status="Closed">Close</button>` : ` <button class="btn btn-small" data-action="change-state" data-id="${item.id}" data-status="Published">Publish</button>`}</td></tr>`), "No assignments yet.")}
    </section><div id="submission-panel"></div>`;
  attachProfessorActions(area, ownSubjects, assignments);
}

function attachProfessorActions(area, knownSubjects = [], assignments = []) {
  area.querySelectorAll("[data-action='new-assignment']").forEach((button) => button.addEventListener("click", async () => {
    let subjects = knownSubjects;
    if (!subjects.length) {
      try {
        subjects = await request("/professor/subjects");
      } catch (error) {
        showToast(error.message, true);
        return;
      }
    }
    if (!subjects.length) {
      showToast("No assigned subjects are available. Ask an administrator to map your subject.", true);
      return;
    }
    openAssignmentForm(subjects);
  }));
  area.querySelectorAll("[data-action='view-submissions']").forEach((button) => button.addEventListener("click", async () => {
    try {
      const items = await request(`/professor/assignments/${button.dataset.id}/submissions`);
      const panel = document.getElementById("submission-panel");
      if (!panel) {
        currentPage = "assignments";
        await renderProfessorAssignments(document.getElementById("page-content"));
        document.querySelector(`#page-content [data-action="view-submissions"][data-id="${button.dataset.id}"]`)?.click();
        return;
      }
      panel.innerHTML = `<section class="panel"><div class="panel-heading"><div><h2>Submissions</h2><p>${items.length} students in this academic group</p></div></div>
        ${table(["Student", "Submitted file", "Time", "Status", "Evaluation"], items.map((item) => `<tr><td>${esc(item.student)}<span class="secondary-cell">${esc(item.login_id)}</span></td><td>${item.id ? `<a href="/api/v1/files/submissions/${item.id}" data-download>${esc(item.file_name)}</a>` : "—"}</td><td>${fmtDate(item.submitted_at, true)}</td><td>${fmtStatus(item.status)}${item.is_late ? '<span class="badge Overdue">Late</span>' : ""}</td><td>${item.id ? item.status === "Evaluated" ? `${esc(item.evaluation.marks)} <button class="btn btn-secondary btn-small" data-action="evaluate" data-id="${item.id}" data-name="${esc(item.student)}">Edit</button>` : `<button class="btn btn-small" data-action="evaluate" data-id="${item.id}" data-name="${esc(item.student)}">Evaluate</button>` : "—"}</td></tr>`), "No students found.")}</section>`;
      panel.querySelectorAll("[data-action='evaluate']").forEach((action) => action.addEventListener("click", () => openEvaluation(action.dataset.id, action.dataset.name)));
    } catch (error) { showToast(error.message, true); }
  }));
  area.querySelectorAll("[data-action='publish']").forEach((button) => button.addEventListener("click", async () => {
    try {
      await request(`/professor/assignments/${button.dataset.id}`, { method: "PUT", body: JSON.stringify({ status: "Published" }) });
      showToast("Assignment published. Eligible students have been notified.");
      await renderProfessorAssignments(document.getElementById("page-content"));
    } catch (error) { showToast(error.message, true); }
  }));
  area.querySelectorAll("[data-action='edit-assignment']").forEach((button) => button.addEventListener("click", () => {
    const assignment = assignments.find((item) => String(item.id) === button.dataset.id);
    if (assignment) openAssignmentForm(knownSubjects, assignment);
  }));
  area.querySelectorAll("[data-action='change-state']").forEach((button) => button.addEventListener("click", async () => {
    try {
      await request(`/professor/assignments/${button.dataset.id}`, {
        method: "PUT",
        body: JSON.stringify({ status: button.dataset.status }),
      });
      showToast(`Assignment ${button.dataset.status.toLowerCase()}.`);
      await renderProfessorAssignments(document.getElementById("page-content"));
    } catch (error) { showToast(error.message, true); }
  }));
}

function openAssignmentForm(subjects, assignment = null) {
  const area = document.getElementById("page-content");
  const old = document.getElementById("assignment-form-panel");
  if (old) old.remove();
  const due = assignment ? new Date(assignment.due_at) : null;
  const localDue = due && !Number.isNaN(due.getTime())
    ? new Date(due.getTime() - due.getTimezoneOffset() * 60000).toISOString().slice(0, 16)
    : "";
  const panel = document.createElement("section");
  panel.id = "assignment-form-panel";
  panel.className = "panel";
  panel.innerHTML = `<div class="panel-heading"><div><h2>${assignment ? "Edit assignment" : "Create assignment"}</h2><p>Choose an assigned subject and set the submission deadline.</p></div><button class="btn btn-secondary btn-small" data-action="close-form">Close</button></div>
    <form id="create-assignment-form"><div class="form-grid">
      <div class="field wide"><label>Title</label><input name="title" maxlength="160" value="${esc(assignment?.title || "")}" required></div>
      <div class="field wide"><label>Instructions</label><textarea name="description" maxlength="5000" required>${esc(assignment?.description || "")}</textarea></div>
      <div class="field"><label>Subject</label><select name="subject_id" ${assignment ? "disabled" : ""} required>${subjects.map((s) => `<option value="${s.id}" data-dept="${s.department_id}" data-sem="${s.semester_id}" ${assignment?.subject_id === s.id ? "selected" : ""}>${esc(s.code)} · ${esc(s.name)} (Semester ${s.semester})</option>`).join("")}</select></div>
      <div class="field"><label>Due date and time</label><input name="due_at" type="datetime-local" value="${localDue}" required></div>
      <div class="field"><label>Maximum marks</label><input name="max_marks" type="number" min="1" max="10000" value="${esc(assignment?.max_marks ?? 100)}" required></div>
      ${assignment ? `<div class="field"><label>Publication state</label><select name="status"><option ${assignment.status === "Draft" ? "selected" : ""}>Draft</option><option ${assignment.status === "Published" ? "selected" : ""}>Published</option><option ${assignment.status === "Closed" ? "selected" : ""}>Closed</option></select></div>` : `<div class="field"><label>Reference document (optional)</label><input name="reference" type="file" accept=".pdf,.docx"></div>`}
      <div class="field"><label><input name="allow_late" type="checkbox" ${assignment?.allow_late === false ? "" : "checked"}> Allow late submissions</label></div>
      <div class="field"><label><input name="allow_resubmission" type="checkbox" ${assignment?.allow_resubmission === false ? "" : "checked"}> Allow resubmissions</label></div>
    </div><div class="form-actions"><button class="btn" type="submit">${assignment ? "Save changes" : "Save as draft"}</button>${assignment ? "" : '<button class="btn btn-secondary" type="button" data-action="save-publish">Publish now</button>'}</div></form>`;
  area.prepend(panel);
  panel.querySelector("[data-action='close-form']").addEventListener("click", () => panel.remove());
  const send = async (publish) => {
    const form = panel.querySelector("form");
    if (!form.reportValidity()) return;
    if (assignment) {
      try {
        await request(`/professor/assignments/${assignment.id}`, {
          method: "PUT",
          body: JSON.stringify({
            title: form.elements.title.value,
            description: form.elements.description.value,
            due_at: new Date(form.elements.due_at.value).toISOString(),
            max_marks: Number(form.elements.max_marks.value),
            status: form.elements.status.value,
            allow_late: form.elements.allow_late.checked,
            allow_resubmission: form.elements.allow_resubmission.checked,
          }),
        });
        showToast("Assignment updated.");
        await renderProfessorAssignments(document.getElementById("page-content"));
      } catch (error) { showToast(error.message, true); }
      return;
    }
    const subjectOption = form.elements.subject_id.selectedOptions[0];
    const values = {
      title: form.elements.title.value,
      description: form.elements.description.value,
      subject_id: Number(form.elements.subject_id.value),
      department_id: Number(subjectOption.dataset.dept),
      semester_id: Number(subjectOption.dataset.sem),
      due_at: new Date(form.elements.due_at.value).toISOString(),
      max_marks: Number(form.elements.max_marks.value),
      status: publish ? "Published" : "Draft",
      allow_late: form.elements.allow_late.checked,
      allow_resubmission: form.elements.allow_resubmission.checked,
    };
    const data = new FormData();
    for (const [key, value] of Object.entries(values)) data.append(key, String(value));
    if (form.elements.reference.files[0]) data.append("reference", form.elements.reference.files[0]);
    try {
      await request("/professor/assignments", { method: "POST", body: data });
      showToast(publish ? "Assignment published." : "Draft saved.");
      await renderProfessorAssignments(document.getElementById("page-content"));
    } catch (error) { showToast(error.message, true); }
  };
  panel.querySelector("form").addEventListener("submit", (event) => { event.preventDefault(); send(false); });
  panel.querySelector("[data-action='save-publish']").addEventListener("click", () => send(true));
}

function openEvaluation(id, student) {
  const marks = window.prompt(`Marks for ${student} (0 to maximum marks):`);
  if (marks === null) return;
  const feedback = window.prompt("Feedback for the student:", "") ?? "";
  request(`/professor/submissions/${id}/evaluation`, {
    method: "POST",
    body: JSON.stringify({ marks: Number(marks), feedback, publish: true }),
  }).then(() => {
    showToast("Evaluation published to the student.");
    document.querySelector("[data-action='view-submissions']")?.click();
  }).catch((error) => showToast(error.message, true));
}

async function renderUsers(area) {
  const [users, departments, semesters] = await Promise.all([
    request("/admin/users"), request("/admin/departments"), request("/admin/semesters"),
  ]);
  area.innerHTML = `${heading("User management", "Create accounts, update academic groups and deactivate access.")}
    <section class="panel"><div class="panel-heading"><div><h2>Add a user</h2><p>Student accounts require a department and semester.</p></div></div>
      <form id="create-user-form"><div class="form-grid">
        <div class="field"><label>Full name</label><input name="full_name" required></div><div class="field"><label>Role</label><select name="role"><option value="student">Student</option><option value="professor">Professor</option><option value="admin">Administrator</option></select></div>
        <div class="field"><label>USN / Faculty ID / Admin ID</label><input name="login_id" required></div><div class="field"><label>College email</label><input name="email" type="email" required></div>
        <div class="field"><label>Temporary password <span class="muted">(leave blank when editing)</span></label><input name="password" type="password" minlength="8" required></div>
        <div class="field"><label>Department</label><select name="department_id"><option value="">Select department</option>${departments.map((d) => `<option value="${d.id}">${esc(d.code)} · ${esc(d.name)}</option>`).join("")}</select></div>
        <div class="field"><label>Semester</label><select name="semester_id"><option value="">Select semester</option>${semesters.map((s) => `<option value="${s.id}">${esc(s.department)} · Semester ${s.number} · ${esc(s.academic_year)}</option>`).join("")}</select></div>
      </div><div class="form-actions"><button class="btn" type="submit">Create account</button><button class="btn btn-secondary" type="button" id="cancel-user-edit" hidden>Cancel edit</button></div></form>
    </section><section class="panel"><div class="panel-heading"><div><h2>Registered users</h2><p>${users.length} accounts</p></div></div>
      ${table(["Name / login", "Role", "Department / semester", "Status", "Action"], users.map((user) => `<tr><td><span class="primary-cell">${esc(user.full_name)}</span><span class="secondary-cell">${esc(user.login_id)} · ${esc(user.email)}</span></td><td>${esc(user.role)}</td><td>${esc(user.department || "—")} ${user.semester ? `· Sem ${user.semester}` : ""}</td><td>${fmtStatus(user.is_active ? "Active" : "Inactive")}</td><td><button class="btn btn-secondary btn-small" data-action="edit-user" data-id="${user.id}">Edit</button> <button class="btn btn-secondary btn-small" data-action="toggle-user" data-id="${user.id}" data-active="${user.is_active}">${user.is_active ? "Deactivate" : "Activate"}</button></td></tr>`), "No users found.")}</section>`;
  document.getElementById("create-user-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const data = Object.fromEntries(form);
    data.department_id = data.department_id ? Number(data.department_id) : null;
    data.semester_id = data.semester_id ? Number(data.semester_id) : null;
    const userId = event.currentTarget.dataset.editId;
    if (!data.password) delete data.password;
    if (userId) delete data.role;
    try {
      await request(userId ? `/admin/users/${userId}` : "/admin/users", {
        method: userId ? "PUT" : "POST",
        body: JSON.stringify(data),
      });
      showToast(userId ? "User updated." : "User created.");
      await renderUsers(area);
    }
    catch (error) { showToast(error.message, true); }
  });
  area.querySelectorAll("[data-action='edit-user']").forEach((button) => button.addEventListener("click", () => {
    const user = users.find((item) => String(item.id) === button.dataset.id);
    if (!user) return;
    const form = document.getElementById("create-user-form");
    form.dataset.editId = String(user.id);
    form.elements.full_name.value = user.full_name;
    form.elements.role.value = user.role;
    form.elements.role.disabled = true;
    form.elements.login_id.value = user.login_id;
    form.elements.email.value = user.email;
    form.elements.password.required = false;
    form.elements.department_id.value = user.department_id || "";
    form.elements.semester_id.value = user.semester_id || "";
    form.querySelector("button[type='submit']").textContent = "Save user changes";
    document.getElementById("cancel-user-edit").hidden = false;
    form.scrollIntoView({ behavior: "smooth", block: "start" });
    form.elements.full_name.focus();
  }));
  document.getElementById("cancel-user-edit").addEventListener("click", () => {
    renderUsers(area);
  });
  area.querySelectorAll("[data-action='toggle-user']").forEach((button) => button.addEventListener("click", async () => {
    try {
      await request(`/admin/users/${button.dataset.id}`, { method: "PUT", body: JSON.stringify({ is_active: button.dataset.active !== "true" }) });
      showToast("User status updated.");
      await renderUsers(area);
    } catch (error) { showToast(error.message, true); }
  }));
}

async function renderAcademics(area) {
  const [departments, semesters, subjects, users] = await Promise.all([
    request("/admin/departments"), request("/admin/semesters"), request("/admin/subjects"), request("/admin/users"),
  ]);
  const professors = users.filter((user) => user.role === "professor");
  area.innerHTML = `${heading("Academic setup", "Maintain departments, semesters and subjects with professor mappings.")}
    <section class="panel"><div class="panel-heading"><div><h2>Departments</h2></div></div>
      <form id="department-form" class="inline-form"><div class="field"><label>Code</label><input name="code" maxlength="20" required></div><div class="field"><label>Name</label><input name="name" required></div><button class="btn" type="submit">Add department</button></form>
      ${table(["Code", "Department"], departments.map((item) => `<tr><td>${esc(item.code)}</td><td>${esc(item.name)}</td></tr>`), "No departments.")}</section>
    <section class="panel"><div class="panel-heading"><div><h2>Semesters</h2></div></div>
      <form id="semester-form" class="inline-form"><div class="field"><label>Department</label><select name="department_id" required>${departments.map((d) => `<option value="${d.id}">${esc(d.code)}</option>`).join("")}</select></div><div class="field"><label>Semester number</label><input name="number" type="number" min="1" max="12" required></div><div class="field"><label>Academic year</label><input name="academic_year" placeholder="2025-2026" required></div><button class="btn" type="submit">Add semester</button></form>
      ${table(["Department", "Semester", "Academic year"], semesters.map((item) => `<tr><td>${esc(item.department)}</td><td>${item.number}</td><td>${esc(item.academic_year)}</td></tr>`), "No semesters.")}</section>
    <section class="panel"><div class="panel-heading"><div><h2>Subjects</h2><p>Map professors to each subject.</p></div></div>
      <form id="subject-form" class="form-grid"><div class="field"><label>Department</label><select name="department_id" required>${departments.map((d) => `<option value="${d.id}">${esc(d.code)}</option>`).join("")}</select></div><div class="field"><label>Semester</label><select name="semester_id" required>${semesters.map((s) => `<option value="${s.id}">${esc(s.department)} · ${s.number}</option>`).join("")}</select></div>
      <div class="field"><label>Subject code</label><input name="code" required></div><div class="field"><label>Subject name</label><input name="name" required></div><div class="field wide"><label>Professor (optional)</label><select name="professor_id"><option value="">No professor mapped</option>${professors.map((p) => `<option value="${p.id}">${esc(p.full_name)}</option>`).join("")}</select></div><div class="field wide"><button class="btn" type="submit">Add subject</button></div></form>
      ${table(["Code", "Subject", "Academic group", "Professor"], subjects.map((item) => `<tr><td>${esc(item.code)}</td><td>${esc(item.name)}</td><td>${esc(item.department)} · Semester ${item.semester}</td><td>${esc(item.professor_ids.map((id) => professors.find((p) => p.id === id)?.full_name || "").filter(Boolean).join(", ") || "Not assigned")}</td></tr>`), "No subjects.")}</section>`;
  document.getElementById("department-form").addEventListener("submit", (event) => postForm(event, "/admin/departments", area));
  document.getElementById("semester-form").addEventListener("submit", (event) => {
    event.preventDefault();
    const data = Object.fromEntries(new FormData(event.currentTarget));
    data.department_id = Number(data.department_id); data.number = Number(data.number);
    sendAcademic("/admin/semesters", data, area);
  });
  document.getElementById("subject-form").addEventListener("submit", (event) => {
    event.preventDefault();
    const data = Object.fromEntries(new FormData(event.currentTarget));
    data.department_id = Number(data.department_id); data.semester_id = Number(data.semester_id);
    data.professor_ids = data.professor_id ? [Number(data.professor_id)] : [];
    delete data.professor_id;
    sendAcademic("/admin/subjects", data, area);
  });
}

async function postForm(event, path, area) {
  event.preventDefault();
  await sendAcademic(path, Object.fromEntries(new FormData(event.currentTarget)), area);
}

async function sendAcademic(path, data, area) {
  try { await request(path, { method: "POST", body: JSON.stringify(data) }); showToast("Academic record added."); await renderAcademics(area); }
  catch (error) { showToast(error.message, true); }
}

async function renderNotifications(area) {
  const items = await request("/student/notifications");
  area.innerHTML = `${heading("Notifications", "Updates for assignments, submissions and published evaluations.")}
    <section class="panel">${items.length ? items.map((item) => `<article class="notification"><p>${esc(item.message)} ${item.read ? "" : '<span class="badge Submitted">New</span>'}</p><small>${fmtDate(item.created_at, true)}</small>${item.read ? "" : ` <button class="btn btn-secondary btn-small" data-action="mark-read" data-id="${item.id}">Mark read</button>`}</article>`).join("") : '<div class="empty">You are all caught up.</div>'}</section>`;
  area.querySelectorAll("[data-action='mark-read']").forEach((button) => button.addEventListener("click", async () => {
    try { await request(`/notifications/${button.dataset.id}/read`, { method: "POST", body: "{}" }); await renderNotifications(area); }
    catch (error) { showToast(error.message, true); }
  }));
}

async function renderReports(area) {
  area.innerHTML = `${heading("Reports", "Export assignment submission and evaluation data for academic review.")}
    <section class="panel"><div class="panel-heading"><div><h2>Submission report</h2><p>CSV export includes student, academic group, submission status, marks and feedback.</p></div></div>
      <a class="btn" href="/api/v1/admin/reports" data-download>Download CSV report</a></section>
    <div class="notice">Exported data contains student identifiers. Store and share reports according to college privacy policy.</div>`;
}

document.addEventListener("click", (event) => {
  const nav = event.target.closest("[data-page]");
  if (nav && nav.closest("#page-content")) {
    currentPage = nav.dataset.page;
    renderShell();
  }
  const download = event.target.closest("[data-download]");
  if (download && download.getAttribute("href")?.startsWith("/api/v1/")) {
    event.preventDefault();
    fetch(download.href, { credentials: "same-origin" })
      .then(async (response) => {
        if (!response.ok) throw new Error((await response.json()).error.message);
        const blob = await response.blob();
        const objectUrl = URL.createObjectURL(blob);
        const link = document.createElement("a");
        link.href = objectUrl;
        link.download = decodeURIComponent(response.headers.get("content-disposition")?.split("filename=")[1]?.replaceAll('"', "") || "download");
        link.click();
        URL.revokeObjectURL(objectUrl);
      })
      .catch((error) => showToast(error.message, true));
  }
});

async function start() {
  try {
    const csrf = await request("/auth/csrf");
    csrfToken = csrf.csrf_token;
    const data = await request("/auth/me");
    currentUser = data.user;
    await renderShell();
  } catch {
    loginView();
  }
}

start();
