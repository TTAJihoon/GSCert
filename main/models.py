import uuid
from django.db import models


class Job(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    status = models.CharField(max_length=20, default="PENDING")  # PENDING/RUNNING/DONE/ERROR
    final_link = models.URLField(blank=True, null=True)
    error = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]


class DownloadReviewJobStatus(models.TextChoices):
    SCHEDULED = "scheduled", "Scheduled"
    QUEUED = "queued", "Queued"
    RUNNING = "running", "Running"
    COMPLETED = "completed", "Completed"
    FAILED = "failed", "Failed"
    CANCELED = "canceled", "Canceled"


class DownloadReviewProjectStatus(models.TextChoices):
    QUEUED = "queued", "Queued"
    RUNNING = "running", "Running"
    DOWNLOADED = "downloaded", "Downloaded"
    INSPECTING = "inspecting", "Inspecting"
    COMPLETED = "completed", "Completed"
    FAILED = "failed", "Failed"
    SKIPPED = "skipped", "Skipped"


class DownloadReviewProjectReviewStatus(models.TextChoices):
    UNREVIEWED = "unreviewed", "Unreviewed"
    COMPLETED = "completed", "Completed"
    NEEDS_FIX = "needs_fix", "Needs fix"
    HELD = "held", "Held"


class DownloadReviewRuleStatus(models.TextChoices):
    PASS = "pass", "Pass"
    FAIL = "fail", "Fail"
    WARNING = "warning", "Warning"
    ERROR = "error", "Error"


class DownloadReviewRuleSeverity(models.TextChoices):
    ERROR = "error", "Error"
    WARNING = "warning", "Warning"
    INFO = "info", "Info"


class DownloadReviewLogLevel(models.TextChoices):
    DEBUG = "debug", "Debug"
    INFO = "info", "Info"
    WARNING = "warning", "Warning"
    ERROR = "error", "Error"


class DownloadReviewJob(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    center_code = models.CharField(max_length=20, default="sangam", db_index=True)
    status = models.CharField(
        max_length=20,
        choices=DownloadReviewJobStatus.choices,
        default=DownloadReviewJobStatus.SCHEDULED,
        db_index=True,
    )
    requested_at = models.DateTimeField(auto_now_add=True, db_index=True)
    queued_at = models.DateTimeField(blank=True, null=True)
    started_at = models.DateTimeField(blank=True, null=True)
    completed_at = models.DateTimeField(blank=True, null=True)
    canceled_at = models.DateTimeField(blank=True, null=True)
    available_after = models.DateTimeField(blank=True, null=True, db_index=True)
    progress_message = models.CharField(max_length=500, blank=True)
    requested_project_count = models.PositiveIntegerField(default=0)
    completed_project_count = models.PositiveIntegerField(default=0)
    failed_project_count = models.PositiveIntegerField(default=0)
    selected_projects_json = models.JSONField(default=list, blank=True)
    requested_ip = models.GenericIPAddressField(blank=True, null=True)
    last_error_message = models.TextField(blank=True)
    worker_pid = models.PositiveIntegerField(blank=True, null=True)
    worker_host = models.CharField(max_length=255, blank=True)
    worker_heartbeat_at = models.DateTimeField(blank=True, null=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "automation_job"
        ordering = ["requested_at", "id"]
        indexes = [
            models.Index(fields=["status", "requested_at"], name="dr_job_status_req_idx"),
            models.Index(fields=["available_after"], name="dr_job_available_idx"),
            models.Index(fields=["center_code", "status"], name="dr_job_center_status_idx"),
        ]

    def __str__(self):
        return f"{self.id} ({self.status})"


class DownloadReviewProject(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    job = models.ForeignKey(
        DownloadReviewJob,
        on_delete=models.CASCADE,
        related_name="projects",
    )
    center_code = models.CharField(max_length=20, default="sangam", db_index=True)
    project_number = models.CharField(max_length=32, db_index=True)
    ecm_row_json = models.JSONField(default=dict, blank=True)
    status = models.CharField(
        max_length=20,
        choices=DownloadReviewProjectStatus.choices,
        default=DownloadReviewProjectStatus.QUEUED,
        db_index=True,
    )
    review_status = models.CharField(
        max_length=20,
        choices=DownloadReviewProjectReviewStatus.choices,
        default=DownloadReviewProjectReviewStatus.UNREVIEWED,
        db_index=True,
    )
    download_dir = models.TextField(blank=True)
    zip_path = models.TextField(blank=True)
    zip_file_name = models.CharField(max_length=255, blank=True)
    zip_deleted_at = models.DateTimeField(blank=True, null=True)
    current_step = models.CharField(max_length=255, blank=True)
    error_message = models.TextField(blank=True)
    error_detail = models.TextField(blank=True)
    retry_count = models.PositiveSmallIntegerField(default=0)
    started_at = models.DateTimeField(blank=True, null=True)
    completed_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "automation_job_project"
        ordering = ["created_at", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["job", "project_number"],
                name="dr_project_job_number_uniq",
            ),
        ]
        indexes = [
            models.Index(fields=["job", "status"], name="dr_project_job_status_idx"),
            models.Index(fields=["project_number"], name="dr_project_number_idx"),
            models.Index(fields=["center_code", "project_number"], name="dr_project_center_number_idx"),
        ]

    def __str__(self):
        return f"{self.project_number} ({self.status})"


class DownloadReviewRule(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=80, unique=True)
    name = models.CharField(max_length=255)
    target_file_pattern = models.CharField(max_length=255, blank=True)
    target_file_type = models.CharField(max_length=30, default="any")
    rule_type = models.CharField(max_length=80, blank=True)
    config_json = models.JSONField(default=dict, blank=True)
    severity = models.CharField(
        max_length=20,
        choices=DownloadReviewRuleSeverity.choices,
        default=DownloadReviewRuleSeverity.ERROR,
    )
    enabled = models.BooleanField(default=True, db_index=True)
    version = models.CharField(max_length=40, default="1")
    sort_order = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "inspection_rule"
        ordering = ["sort_order", "name", "id"]

    def __str__(self):
        return self.name


class DownloadReviewRuleResult(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    job_project = models.ForeignKey(
        DownloadReviewProject,
        on_delete=models.CASCADE,
        related_name="rule_results",
    )
    rule = models.ForeignKey(
        DownloadReviewRule,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="results",
    )
    rule_code = models.CharField(max_length=80, blank=True)
    rule_name = models.CharField(max_length=255)
    sequence = models.PositiveSmallIntegerField(default=0)
    file_path = models.TextField(blank=True)
    file_name = models.CharField(max_length=255, blank=True)
    status = models.CharField(
        max_length=20,
        choices=DownloadReviewRuleStatus.choices,
        db_index=True,
    )
    expected = models.TextField(blank=True)
    actual = models.TextField(blank=True)
    message = models.TextField(blank=True)
    raw_detail_json = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "inspection_result"
        ordering = ["job_project", "sequence", "id"]
        indexes = [
            models.Index(fields=["job_project", "status"], name="dr_rule_result_status_idx"),
        ]

    def __str__(self):
        return f"{self.rule_name} ({self.status})"


class DownloadReviewLog(models.Model):
    job = models.ForeignKey(
        DownloadReviewJob,
        on_delete=models.CASCADE,
        blank=True,
        null=True,
        related_name="logs",
    )
    job_project = models.ForeignKey(
        DownloadReviewProject,
        on_delete=models.CASCADE,
        blank=True,
        null=True,
        related_name="logs",
    )
    level = models.CharField(
        max_length=20,
        choices=DownloadReviewLogLevel.choices,
        default=DownloadReviewLogLevel.INFO,
        db_index=True,
    )
    event_code = models.CharField(max_length=80, blank=True)
    message = models.TextField()
    detail_json = models.JSONField(default=dict, blank=True)
    admin_only = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = "automation_log"
        ordering = ["created_at", "id"]
        indexes = [
            models.Index(fields=["job", "created_at"], name="dr_log_job_created_idx"),
            models.Index(fields=["job_project", "created_at"], name="dr_log_project_created_idx"),
        ]

    def __str__(self):
        return f"{self.level}: {self.message[:80]}"


class SwData(models.Model):
    """GS 인증 이력 참조 데이터 (reference.db sw_data)."""
    serial_number = models.IntegerField(primary_key=True)
    cert_number = models.TextField(blank=True, default='')
    cert_date = models.TextField(blank=True, default='')
    company = models.TextField(blank=True, default='')
    product = models.TextField(blank=True, default='')
    grade = models.TextField(blank=True, default='')
    test_number = models.TextField(blank=True, default='')
    sw_category = models.TextField(blank=True, default='')
    product_desc = models.TextField(blank=True, default='')
    total_wd = models.TextField(blank=True, default='')
    renewal = models.TextField(blank=True, default='')
    notes = models.TextField(blank=True, default='')
    date_range = models.TextField(blank=True, default='')
    test_lab = models.TextField(blank=True, default='')
    start_date = models.TextField(blank=True, default='')
    end_date = models.TextField(blank=True, default='')

    class Meta:
        app_label = 'main'
        db_table = 'sw_data'

    def __str__(self):
        return f"{self.cert_number} {self.company} {self.product}"


class ReferenceCenterPl(models.Model):
    center_code = models.CharField(max_length=20, db_index=True)
    center_label = models.CharField(max_length=20)
    name = models.CharField(max_length=50, unique=True)
    display_order = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = 'main'
        db_table = 'reference_center_pl'
        ordering = ['center_code', 'display_order', 'name']
        indexes = [
            models.Index(fields=['center_code', 'name'], name='ref_center_pl_code_name_idx'),
        ]

    def __str__(self):
        return f"{self.center_label} {self.name}"


class ReferenceProject(models.Model):
    project_number = models.CharField(max_length=32, unique=True, db_index=True)
    center_code = models.CharField(max_length=20, db_index=True)
    center_label = models.CharField(max_length=20, blank=True, default='')
    cert_date = models.CharField(max_length=20, blank=True, default='')
    cert_committee_date = models.DateField(blank=True, null=True, db_index=True)
    company = models.TextField(blank=True, default='')
    product = models.TextField(blank=True, default='')
    pl = models.TextField(blank=True, default='')
    primary_tester = models.CharField(max_length=50, blank=True, default='', db_index=True)
    wd = models.TextField(blank=True, default='')
    request_date = models.TextField(blank=True, default='')
    contract_date = models.TextField(blank=True, default='')
    start_date = models.TextField(blank=True, default='')
    expected_end_date = models.TextField(blank=True, default='')
    review_result = models.CharField(max_length=20, blank=True, default='')
    inspection_date = models.TextField(blank=True, default='')
    artifact_results_json = models.JSONField(default=dict, blank=True)
    raw_company_product = models.TextField(blank=True, default='')
    source_spreadsheet_id = models.CharField(max_length=120, blank=True, default='')
    source_gid = models.CharField(max_length=40, blank=True, default='')
    source_row_number = models.PositiveIntegerField(blank=True, null=True)
    source_payload_json = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = 'main'
        db_table = 'reference_project'
        ordering = ['-cert_committee_date', 'project_number']
        indexes = [
            models.Index(fields=['center_code', 'cert_committee_date'], name='ref_project_center_date_idx'),
            models.Index(fields=['center_code', 'project_number'], name='ref_project_center_number_idx'),
            models.Index(fields=['primary_tester'], name='ref_project_primary_tester_idx'),
        ]

    def __str__(self):
        return f"{self.project_number} {self.company} {self.product}"


class DownloadReviewLock(models.Model):
    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    locked = models.BooleanField(default=False)
    owner = models.CharField(max_length=80, blank=True)
    job = models.ForeignKey(
        DownloadReviewJob,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="locks",
    )
    locked_at = models.DateTimeField(blank=True, null=True)
    heartbeat_at = models.DateTimeField(blank=True, null=True)
    note = models.CharField(max_length=255, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "automation_lock"

    def __str__(self):
        return f"automation_lock locked={self.locked}"
