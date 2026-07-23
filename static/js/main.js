// static/js/main.js  (updated)
// ------------------------------------------------------------
// Camera + overlay globals
let videoEl = null;
let camStream = null;
let overlay = null;
let octx = null;

// NEW: camera switching/state
let currentDeviceId = null;   // tracks the active camera deviceId
let devicesCache = [];        // cached list of video input devices
let preferredFacing = null;   // "environment" (phones) or "user" (desktops)

// ---------- Helpers ----------
function isMobile() {
  return /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(navigator.userAgent);
}

function isSecureForCamera() {
  // Allowed by browsers: HTTPS, localhost, or 127.0.0.1
  if (window.isSecureContext) return true;
  const h = location.hostname;
  return h === "localhost" || h === "127.0.0.1";
}

// (Optional) If you later enable HTTPS on your LAN,
// you can auto-upgrade when accessed by IP:
// (uncomment to use)
/*
(function enforceHttpsOnLan() {
  const h = location.hostname;
  const looksLikeIP = /^\d{1,3}(\.\d{1,3}){3}$/.test(h);
  if (looksLikeIP && location.protocol !== "https:") {
    location.href = "https://" + location.host + location.pathname + location.search + location.hash;
  }
})();
*/

// Stop any existing camera stream
async function stopCamera() {
  if (camStream) {
    camStream.getTracks().forEach(t => t.stop());
    camStream = null;
  }
  if (videoEl) videoEl.srcObject = null;
}

// Start camera with specific constraints and remember deviceId if available
async function startCameraWithConstraints(constraints) {
  await stopCamera();
  const stream = await navigator.mediaDevices.getUserMedia(constraints);
  camStream = stream;
  videoEl.srcObject = stream;

  try {
    const [track] = stream.getVideoTracks();
    const settings = track && track.getSettings ? track.getSettings() : {};
    if (settings && settings.deviceId) currentDeviceId = settings.deviceId;
  } catch (_) {}
}

// Enumerate cameras and populate the dropdown
async function listCamerasAndPopulate(activeDeviceId) {
  devicesCache = [];
  const sel = document.getElementById("cameraSelect");
  if (!sel || !navigator.mediaDevices || !navigator.mediaDevices.enumerateDevices) return;

  const all = await navigator.mediaDevices.enumerateDevices();
  const videos = all.filter(d => d.kind === "videoinput");
  devicesCache = videos;

  sel.innerHTML = "";
  videos.forEach((d, idx) => {
    const opt = document.createElement("option");
    // Label might be empty until permission is granted
    const hasLabel = d.label && d.label.trim().length;
    const friendly = hasLabel ? d.label : (idx === 0 ? "Camera 1" : `Camera ${idx + 1}`);
    opt.value = d.deviceId;
    opt.textContent = friendly;
    sel.appendChild(opt);
  });

  if (activeDeviceId && videos.some(v => v.deviceId === activeDeviceId)) {
    sel.value = activeDeviceId;
  } else if (videos.length) {
    sel.value = videos[0].deviceId;
  }
}

// ---------- Camera init (UPDATED) ----------
async function initCamera() {
  videoEl = document.getElementById("video");
  if (!videoEl) return;

  const statusEl = document.getElementById("status") || document.getElementById("att-status");

  // Prepare overlay
  overlay = document.getElementById("overlay");
  if (overlay) {
    const syncCanvasSize = () => {
      overlay.width  = videoEl.clientWidth  || videoEl.videoWidth  || 640;
      overlay.height = videoEl.clientHeight || videoEl.videoHeight || 480;
    };
    const ro = new ResizeObserver(syncCanvasSize);
    ro.observe(videoEl);
    videoEl.addEventListener("loadedmetadata", syncCanvasSize);
    window.addEventListener("resize", syncCanvasSize);
    setTimeout(syncCanvasSize, 400);
    octx = overlay.getContext("2d");
  }

  // Decide default facing: phones = back camera, desktops = front camera
  preferredFacing = isMobile() ? "environment" : "user";

  if (!isSecureForCamera()) {
    if (statusEl) {
      statusEl.textContent =
        "Camera blocked on HTTP over LAN. Use HTTPS (recommended) or localhost for dev.";
      statusEl.className = "err";
    }
    // We still try to open camera; without HTTPS or browser override it will fail on IP.
  }

  try {
    // Try ideal facing first
    let constraints = { video: { facingMode: { ideal: preferredFacing } } };

    try {
      await startCameraWithConstraints(constraints);
    } catch (e1) {
      // Some browsers (iOS Safari) prefer exact
      constraints = { video: { facingMode: { exact: preferredFacing } } };
      await startCameraWithConstraints(constraints);
    }

    // Now that permission is granted, list cameras
    await listCamerasAndPopulate(currentDeviceId);

    // Hook dropdown change
    const sel = document.getElementById("cameraSelect");
    if (sel) {
      sel.addEventListener("change", async () => {
        const deviceId = sel.value;
        currentDeviceId = deviceId;
        try {
          await startCameraWithConstraints({ video: { deviceId: { exact: deviceId } } });
        } catch (e) {
          // Fallback to facing mode
          try {
            await startCameraWithConstraints({ video: { facingMode: { ideal: preferredFacing } } });
          } catch (_) {}
        }
        await listCamerasAndPopulate(currentDeviceId);
      });
    }

    // Hook switch button (toggle front/back)
    const switchBtn = document.getElementById("switchCam");
    if (switchBtn) {
      switchBtn.addEventListener("click", async () => {
        preferredFacing = (preferredFacing === "user") ? "environment" : "user";
        try {
          await startCameraWithConstraints({ video: { facingMode: { ideal: preferredFacing } } });
        } catch (e1) {
          try {
            await startCameraWithConstraints({ video: { facingMode: { exact: preferredFacing } } });
          } catch (e2) {
            // Fallback: cycle through device list
            const idx = devicesCache.findIndex(d => d.deviceId === currentDeviceId);
            const next = devicesCache[(idx + 1) % Math.max(1, devicesCache.length)];
            if (next) {
              await startCameraWithConstraints({ video: { deviceId: { exact: next.deviceId } } });
            }
          }
        }
        await listCamerasAndPopulate(currentDeviceId);
      });
    }

    // Keep device list fresh if cams are plugged/unplugged
    if (navigator.mediaDevices && navigator.mediaDevices.addEventListener) {
      navigator.mediaDevices.addEventListener("devicechange", async () => {
        await listCamerasAndPopulate(currentDeviceId);
      });
    }

  } catch (err) {
    if (statusEl) {
      statusEl.textContent = "Camera error: " + (err && err.message ? err.message : String(err));
      statusEl.className = "err";
    }
  }
}

// ---------- Snapshots ----------
function getSnapshotDataURL() {
  if (!videoEl || videoEl.readyState < 2) return null;
  const canvas = document.createElement("canvas");
  canvas.width = videoEl.videoWidth || videoEl.clientWidth || 640;
  canvas.height = videoEl.videoHeight || videoEl.clientHeight || 480;
  const ctx = canvas.getContext("2d");
  ctx.drawImage(videoEl, 0, 0, canvas.width, canvas.height);
  return canvas.toDataURL("image/jpeg", 0.6); // smaller upload for smoother loop
}

// ---------- Drawing ----------
function drawBoxes(boxes) {
  if (!octx || !overlay || !videoEl) return;

  const srcW = videoEl.videoWidth || overlay.width;
  const srcH = videoEl.videoHeight || overlay.height;
  const dstW = overlay.width;
  const dstH = overlay.height;
  const scaleX = dstW / srcW;
  const scaleY = dstH / srcH;

  octx.clearRect(0, 0, dstW, dstH);

  boxes.forEach(b => {
    const color = b.known ? "rgba(0,180,0,1)" : "rgba(220,0,0,1)";
    octx.lineWidth = 3;
    octx.strokeStyle = color;
    octx.fillStyle = color;

    const x = Math.round(b.left * scaleX);
    const y = Math.round(b.top * scaleY);
    const w = Math.round((b.right - b.left) * scaleX);
    const h = Math.round((b.bottom - b.top) * scaleY);

    octx.strokeRect(x, y, w, h);

    const label = b.label || (b.known ? "Detected" : "Unknown");
    octx.font = "14px sans-serif";
    const textW = Math.max(60, Math.ceil(octx.measureText(label).width + 14));
    const barH = 20;
    octx.fillRect(x, y + h - barH, textW, barH);
    octx.fillStyle = "white";
    octx.fillText(label, x + 6, y + h - 6);
  });
}

/* ---------- Registration preview ---------- */
let detectTimer = null;
function startDetectPreview() {
  const statusEl = document.getElementById("status");
  if (detectTimer) clearInterval(detectTimer);
  detectTimer = setInterval(async () => {
    const img = getSnapshotDataURL();
    if (!img) return;
    try {
      const res = await fetch("/api/detect_faces", {
        method: "POST", headers: {"Content-Type":"application/json"},
        body: JSON.stringify({ image: img })
      });
      const data = await res.json();
      if (res.ok) {
        const boxes = (data.faces || []).map(f => ({...f, known: true, label:"Face Detected"}));
        drawBoxes(boxes);
        if (statusEl) {
          statusEl.textContent = boxes.length ? "Face detected. Click Capture & Register." : "Looking for a face…";
          statusEl.className = boxes.length ? "ok" : "";
        }
      } else {
        if (statusEl) { statusEl.textContent = "Detection error"; statusEl.className = "err"; }
      }
    } catch(e) {}
  }, 250);
}

async function captureStudent() {
  const name = document.getElementById("studentName").value.trim();
  const sid  = document.getElementById("studentId").value.trim();
  const statusEl = document.getElementById("status");

  if (!name || !sid) {
    statusEl.textContent = "Please enter student name and ID.";
    statusEl.className = "err";
    return;
  }

  statusEl.textContent = "Scanning for face...";
  statusEl.className = "";

  const image = getSnapshotDataURL();
  if (!image) {
    statusEl.textContent = "Camera not ready.";
    statusEl.className = "err";
    return;
  }

  try {
    const res = await fetch("/api/encode_face", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, id: sid, image })
    });
    const data = await res.json();
    if (res.ok) {
      statusEl.textContent = data.message || "Student registered";
      statusEl.className = "ok";
      document.getElementById("studentName").value = "";
      document.getElementById("studentId").value = "";
    } else {
      statusEl.textContent = data.error || "Registration failed";
      statusEl.className = "err";
    }
  } catch (e) {
    statusEl.textContent = "Network error.";
    statusEl.className = "err";
  }
}

/* ---------- Take Attendance: faster loop + no overlap + stale clear ---------- */
let attendanceTimer = null;
let staleClearTimer = null;
let lastBoxesAt = 0;
let inFlight = false;

function renderSchedule(schedule) {
  if (!schedule || !schedule.length) return "No schedule set.";
  return schedule.map(s => `${s.day} (${s.start_time} - ${s.end_time})`).join(", ");
}

function startAttendance() {
  const course = document.getElementById("course").value.trim();
  const list = document.getElementById("recognized");
  const status = document.getElementById("att-status");
  const schedText = document.getElementById("scheduleText");

  if (!course) {
    status.textContent = "Please select a course.";
    status.className = "err";
    return;
  }

  stopAttendance(); // clean state
  status.textContent = "Attendance started. Scanning…";
  status.className = "";

  attendanceTimer = setInterval(async () => {
    if (inFlight) return;
    const image = getSnapshotDataURL();
    if (!image) return;

    inFlight = true;
    try {
      const res = await fetch("/api/recognize_face", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ course, image })
      });
      const data = await res.json();

      if (!res.ok) {
        drawBoxes([]);
        lastBoxesAt = performance.now();
        if (res.status === 409) {
          status.textContent = "Not the scheduled time for this course.";
          status.className = "err";
          if (schedText) schedText.textContent = renderSchedule(data.schedule);
        } else {
          status.textContent = data.error || "Error recording attendance";
          status.className = "err";
        }
        return;
      }

      drawBoxes(data.faces || []);
      lastBoxesAt = performance.now();
      if (schedText) schedText.textContent = renderSchedule(data.schedule);

      (data.recent || []).forEach(r => {
        const li = document.createElement("li");
        li.textContent = `${r.student_name} (${r.student_id}) • ${r.timestamp}`;
        list.prepend(li);
        while (list.children.length > 10) list.removeChild(list.lastChild);
      });
    } catch (e) {
      status.textContent = "Network error during attendance";
      status.className = "err";
    } finally {
      inFlight = false;
    }
  }, 300);

  staleClearTimer = setInterval(() => {
    if (!octx) return;
    if (performance.now() - lastBoxesAt > 600) {
      drawBoxes([]);
      lastBoxesAt = performance.now();
    }
  }, 200);
}

function stopAttendance() {
  const status = document.getElementById("att-status");
  if (attendanceTimer) clearInterval(attendanceTimer);
  if (staleClearTimer) clearInterval(staleClearTimer);
  attendanceTimer = null;
  staleClearTimer = null;
  inFlight = false;
  drawBoxes([]); // clear immediately
  if (status) {
    status.textContent = "Attendance stopped.";
    status.className = "";
  }
}

/* ---------- View Attendance (table) ---------- */
async function viewCourseRecords() {
  const course = document.getElementById("course").value.trim();
  const date = document.getElementById("dateFilter")?.value;
  const tbody = document.querySelector("#recordsTable tbody");
  const status = document.getElementById("att-status") || {textContent: "", className: ""};
  if (!course) {
    status.textContent = "Select a course first.";
    status.className = "err";
    return;
  }
  let url = `/attendance/${encodeURIComponent(course)}`;
  if (date) url += `?date=${date}`;
  const res = await fetch(url);
  const data = await res.json();
  if (!res.ok) {
    status.textContent = data.error || "Unable to load records.";
    status.className = "err";
    return;
  }
  tbody.innerHTML = "";
  data.forEach(r => {
    const tr = document.createElement("tr");
    tr.innerHTML = `<td>${r.student_id}</td><td>${r.student_name || "N/A"}</td><td>${r.course}</td><td>${r.status}</td><td>${r.timestamp}</td>`;
    tbody.appendChild(tr);
  });
}

// ---------- Boot ----------
window.addEventListener("DOMContentLoaded", () => {
  // Expect your HTML to include:
  // <video id="video" autoplay playsinline muted></video>
  // <canvas id="overlay"></canvas>
  // <select id="cameraSelect"></select>
  // <button id="switchCam">Switch</button>
  initCamera();
  if (document.getElementById("capture-page")) {
    startDetectPreview();
  }
});
