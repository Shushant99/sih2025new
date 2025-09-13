// static/js/admin_reports.js
let currentOverviewPage = 1;
let currentAttendancePage = 1;

document.addEventListener('DOMContentLoaded', function() {
    // Load initial data
    loadClasses();
    loadStudentsOverview();
    loadStatistics();

    // Set default date filters (last 30 days)
    const today = new Date();
    const thirtyDaysAgo = new Date(today.getTime() - (30 * 24 * 60 * 60 * 1000));
    document.getElementById('attendanceDateTo').value = today.toISOString().split('T')[0];
    document.getElementById('attendanceDateFrom').value = thirtyDaysAgo.toISOString().split('T')[0];

    // Tab change listeners
    document.getElementById('attendance-tab').addEventListener('shown.bs.tab', function() {
        loadAttendanceRecords();
    });
});

function loadClasses() {
    fetch('/api/classes')
        .then(response => response.json())
        .then(classes => {
            const overviewClassFilter = document.getElementById('overviewClassFilter');
            const attendanceClassFilter = document.getElementById('attendanceClassFilter');

            classes.forEach(className => {
                const option1 = document.createElement('option');
                option1.value = className;
                option1.textContent = className;
                overviewClassFilter.appendChild(option1);

                const option2 = document.createElement('option');
                option2.value = className;
                option2.textContent = className;
                attendanceClassFilter.appendChild(option2);
            });
        });
}

function loadStudentsOverview(page = 1) {
    const className = document.getElementById('overviewClassFilter').value;
    const search = document.getElementById('overviewSearchInput').value;

    const params = new URLSearchParams({
        page: page,
        per_page: 20,
        class: className,
        search: search
    });

    fetch(`/api/admin/students-overview?${params}`)
        .then(response => response.json())
        .then(data => {
            renderStudentsGrid(data.students);
            renderOverviewPagination(data);
            updateOverviewResultsInfo(data);
            currentOverviewPage = page;
        })
        .catch(error => {
            console.error('Error loading students:', error);
            showAlert('Error loading students data', 'danger');
        });
}

function renderStudentsGrid(students) {
    const grid = document.getElementById('studentsGrid');
    grid.innerHTML = '';

    students.forEach(student => {
        const col = document.createElement('div');
        col.className = 'col-md-6 col-lg-4 mb-3';

        const attendanceClass = getAttendanceClass(student.attendance_percentage);
        const totalSamples = student.total_samples || 0;

        col.innerHTML = `
            <div class="student-card h-100" onclick="showStudentDetail('${student.student_id}', '${student.student_name}')">
                <div class="d-flex justify-content-between align-items-start mb-2">
                    <h6 class="mb-0">${student.student_name}</h6>
                    <span class="badge bg-secondary">${student.class_name}</span>
                </div>
                <p class="text-muted mb-2">ID: ${student.student_id}</p>

                <div class="row text-center mb-3">
                    <div class="col-4">
                        <div class="sample-status-approved">
                            <i class="fas fa-check-circle"></i><br>
                            <small>${student.approved_samples}</small><br>
                            <small>Approved</small>
                        </div>
                    </div>
                    <div class="col-4">
                        <div class="sample-status-pending">
                            <i class="fas fa-clock"></i><br>
                            <small>${student.pending_samples}</small><br>
                            <small>Pending</small>
                        </div>
                    </div>
                    <div class="col-4">
                        <div class="sample-status-rejected">
                            <i class="fas fa-times-circle"></i><br>
                            <small>${student.rejected_samples}</small><br>
                            <small>Rejected</small>
                        </div>
                    </div>
                </div>

                <div class="d-flex justify-content-between align-items-center">
                    <small class="text-muted">
                        Classes: ${student.present_count}/${student.total_classes}
                    </small>
                    <span class="${attendanceClass}">
                        ${student.attendance_percentage}%
                    </span>
                </div>

                <div class="mt-2">
                    <small class="text-muted">
                        Last Upload: ${student.last_upload ? new Date(student.last_upload).toLocaleDateString() : 'Never'}
                    </small>
                </div>
            </div>
        `;
        grid.appendChild(col);
    });
}

function getAttendanceClass(percentage) {
    if (percentage >= 80) return 'attendance-high';
    if (percentage >= 60) return 'attendance-medium';
    return 'attendance-low';
}

function renderOverviewPagination(data) {
    const pagination = document.getElementById('overviewPagination');
    pagination.innerHTML = '';

    // Previous button
    const prevLi = document.createElement('li');
    prevLi.className = `page-item ${data.page === 1 ? 'disabled' : ''}`;
    prevLi.innerHTML = `<a class="page-link" href="#" onclick="loadStudentsOverview(${data.page - 1})">Previous</a>`;
    pagination.appendChild(prevLi);

    // Page numbers
    for (let i = 1; i <= data.total_pages; i++) {
        const li = document.createElement('li');
        li.className = `page-item ${i === data.page ? 'active' : ''}`;
        li.innerHTML = `<a class="page-link" href="#" onclick="loadStudentsOverview(${i})">${i}</a>`;
        pagination.appendChild(li);
    }

    // Next button
    const nextLi = document.createElement('li');
    nextLi.className = `page-item ${data.page === data.total_pages ? 'disabled' : ''}`;
    nextLi.innerHTML = `<a class="page-link" href="#" onclick="loadStudentsOverview(${data.page + 1})">Next</a>`;
    pagination.appendChild(nextLi);
}

function updateOverviewResultsInfo(data) {
    const info = document.getElementById('overviewResultsInfo');
    const start = (data.page - 1) * data.per_page + 1;
    const end = Math.min(data.page * data.per_page, data.total);
    info.textContent = `Showing ${start}-${end} of ${data.total} students`;
}

function loadAttendanceRecords(page = 1) {
    const className = document.getElementById('attendanceClassFilter').value;
    const dateFrom = document.getElementById('attendanceDateFrom').value;
    const dateTo = document.getElementById('attendanceDateTo').value;

    const params = new URLSearchParams({
        page: page,
        per_page: 50,
        class: className,
        date_from: dateFrom,
        date_to: dateTo
    });

    fetch(`/api/admin/attendance-records?${params}`)
        .then(response => response.json())
        .then(data => {
            renderAttendanceTable(data.records);
            renderAttendancePagination(data);
            updateAttendanceResultsInfo(data);
            currentAttendancePage = page;
        })
        .catch(error => {
            console.error('Error loading attendance:', error);
            showAlert('Error loading attendance data', 'danger');
        });
}

function renderAttendanceTable(records) {
    const tbody = document.getElementById('attendanceTableBody');
    tbody.innerHTML = '';

    records.forEach(record => {
        const row = document.createElement('tr');
        const statusClass = record.status === 'Present' ? 'text-success' : 'text-danger';
        const confidence = record.confidence ? `${(record.confidence * 100).toFixed(1)}%` : 'N/A';

        row.innerHTML = `
            <td>${record.student_name}</td>
            <td><span class="badge bg-info">${record.class_name}</span></td>
            <td>${new Date(record.date).toLocaleDateString()}</td>
            <td>${record.time}</td>
            <td><span class="${statusClass}"><strong>${record.status}</strong></span></td>
            <td>${confidence}</td>
        `;
        tbody.appendChild(row);
    });
}

function renderAttendancePagination(data) {
    const pagination = document.getElementById('attendancePagination');
    pagination.innerHTML = '';

    // Previous button
    const prevLi = document.createElement('li');
    prevLi.className = `page-item ${data.page === 1 ? 'disabled' : ''}`;
    prevLi.innerHTML = `<a class="page-link" href="#" onclick="loadAttendanceRecords(${data.page - 1})">Previous</a>`;
    pagination.appendChild(prevLi);

    // Page numbers
    for (let i = 1; i <= data.total_pages; i++) {
        const li = document.createElement('li');
        li.className = `page-item ${i === data.page ? 'active' : ''}`;
        li.innerHTML = `<a class="page-link" href="#" onclick="loadAttendanceRecords(${i})">${i}</a>`;
        pagination.appendChild(li);
    }

    // Next button
    const nextLi = document.createElement('li');
    nextLi.className = `page-item ${data.page === data.total_pages ? 'disabled' : ''}`;
    nextLi.innerHTML = `<a class="page-link" href="#" onclick="loadAttendanceRecords(${data.page + 1})">Next</a>`;
    pagination.appendChild(nextLi);
}

function updateAttendanceResultsInfo(data) {
    const info = document.getElementById('attendanceResultsInfo');
    const start = (data.page - 1) * data.per_page + 1;
    const end = Math.min(data.page * data.per_page, data.total);
    info.textContent = `Showing ${start}-${end} of ${data.total} records`;
}

function loadStatistics() {
    fetch('/api/admin/class-statistics')
        .then(response => response.json())
        .then(data => {
            renderStatistics(data);
        })
        .catch(error => {
            console.error('Error loading statistics:', error);
            showAlert('Error loading statistics', 'danger');
        });
}

function renderStatistics(data) {
    const content = document.getElementById('statisticsContent');
    content.innerHTML = '';

    // Sample Images Statistics
    if (data.sample_stats && data.sample_stats.length > 0) {
        content.innerHTML += `
            <div class="col-12 mb-4">
                <h4><i class="fas fa-images"></i> Sample Images by Class</h4>
                <div class="table-responsive">
                    <table class="table table-striped">
                        <thead class="table-dark">
                            <tr>
                                <th>Class</th>
                                <th>Students</th>
                                <th>Total Samples</th>
                                <th>Approved</th>
                                <th>Pending</th>
                                <th>Rejected</th>
                                <th>Approval Rate</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${data.sample_stats.map(stat => {
                                const approvalRate = stat.total_samples > 0 ? 
                                    ((stat.approved_samples / stat.total_samples) * 100).toFixed(1) : '0.0';
                                return `
                                    <tr>
                                        <td><strong>${stat.class_name}</strong></td>
                                        <td>${stat.total_students}</td>
                                        <td>${stat.total_samples}</td>
                                        <td><span class="sample-status-approved">${stat.approved_samples}</span></td>
                                        <td><span class="sample-status-pending">${stat.pending_samples}</span></td>
                                        <td><span class="sample-status-rejected">${stat.rejected_samples}</span></td>
                                        <td><strong>${approvalRate}%</strong></td>
                                    </tr>
                                `;
                            }).join('')}
                        </tbody>
                    </table>
                </div>
            </div>
        `;
    }

    // Attendance Statistics
    if (data.attendance_stats && data.attendance_stats.length > 0) {
        content.innerHTML += `
            <div class="col-12">
                <h4><i class="fas fa-calendar-check"></i> Attendance by Class</h4>
                <div class="table-responsive">
                    <table class="table table-striped">
                        <thead class="table-dark">
                            <tr>
                                <th>Class</th>
                                <th>Students</th>
                                <th>Total Records</th>
                                <th>Present Records</th>
                                <th>Class Days</th>
                                <th>Attendance Rate</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${data.attendance_stats.map(stat => {
                                const attendanceRate = stat.total_records > 0 ? 
                                    ((stat.present_records / stat.total_records) * 100).toFixed(1) : '0.0';
                                const attendanceClass = getAttendanceClass(parseFloat(attendanceRate));
                                return `
                                    <tr>
                                        <td><strong>${stat.class_name}</strong></td>
                                        <td>${stat.unique_students}</td>
                                        <td>${stat.total_records}</td>
                                        <td>${stat.present_records}</td>
                                        <td>${stat.unique_dates}</td>
                                        <td><span class="${attendanceClass}">${attendanceRate}%</span></td>
                                    </tr>
                                `;
                            }).join('')}
                        </tbody>
                    </table>
                </div>
            </div>
        `;
    }
}

function showStudentDetail(studentId, studentName) {
    fetch(`/api/admin/student-detail/${studentId}`)
        .then(response => response.json())
        .then(data => {
            const modalContent = document.getElementById('studentDetailContent');

            modalContent.innerHTML = `
                <h5>${studentName} (${studentId})</h5>
                <div class="row">
                    <div class="col-md-6">
                        <h6><i class="fas fa-images"></i> Sample Images</h6>
                        <div class="table-responsive">
                            <table class="table table-sm">
                                <thead>
                                    <tr>
                                        <th>Image</th>
                                        <th>Upload Date</th>
                                        <th>Status</th>
                                        <th>Quality</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    ${data.sample_images.map(img => {
                                        const statusBadge = img.status === 'approved' ? 'bg-success' :
                                                          img.status === 'pending' ? 'bg-warning' : 'bg-danger';
                                        const quality = img.quality_score ? `${(img.quality_score * 100).toFixed(0)}%` : 'N/A';
                                        return `
                                            <tr>
                                                <td>
                                                    <img src="/uploads/samples/${img.image_filename}" 
                                                         style="width: 50px; height: 50px; object-fit: cover; border-radius: 4px;">
                                                </td>
                                                <td>${new Date(img.upload_date).toLocaleDateString()}</td>
                                                <td><span class="badge ${statusBadge}">${img.status}</span></td>
                                                <td>${quality}</td>
                                            </tr>
                                        `;
                                    }).join('')}
                                </tbody>
                            </table>
                        </div>
                    </div>
                    <div class="col-md-6">
                        <h6><i class="fas fa-calendar-check"></i> Recent Attendance</h6>
                        <div class="table-responsive">
                            <table class="table table-sm">
                                <thead>
                                    <tr>
                                        <th>Date</th>
                                        <th>Time</th>
                                        <th>Status</th>
                                        <th>Confidence</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    ${data.attendance_records.map(record => {
                                        const statusClass = record.status === 'Present' ? 'text-success' : 'text-danger';
                                        const confidence = record.confidence ? `${(record.confidence * 100).toFixed(1)}%` : 'N/A';
                                        return `
                                            <tr>
                                                <td>${new Date(record.date).toLocaleDateString()}</td>
                                                <td>${record.time}</td>
                                                <td><span class="${statusClass}">${record.status}</span></td>
                                                <td>${confidence}</td>
                                            </tr>
                                        `;
                                    }).join('')}
                                </tbody>
                            </table>
                        </div>
                    </div>
                </div>
            `;

            new bootstrap.Modal(document.getElementById('studentDetailModal')).show();
        });
}

function exportData(type) {
    if (type === 'students') {
        window.open('/api/admin/students-overview?export=csv', '_blank');
    } else if (type === 'attendance') {
        const className = document.getElementById('attendanceClassFilter').value;
        const dateFrom = document.getElementById('attendanceDateFrom').value;
        const dateTo = document.getElementById('attendanceDateTo').value;
        const params = new URLSearchParams({
            export: 'csv',
            class: className,
            date_from: dateFrom,
            date_to: dateTo
        });
        window.open(`/api/admin/attendance-records?${params}`, '_blank');
    }
}

function showAlert(message, type) {
    const alertDiv = document.createElement('div');
    alertDiv.className = `alert alert-${type} alert-dismissible fade show`;
    alertDiv.innerHTML = `
        ${message}
        <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
    `;

    document.querySelector('.container-fluid').insertBefore(alertDiv, document.querySelector('.row'));

    setTimeout(() => {
        alertDiv.remove();
    }, 5000);
}

// Search on Enter key for overview
document.getElementById('overviewSearchInput').addEventListener('keypress', function(e) {
    if (e.key === 'Enter') {
        loadStudentsOverview();
    }
});