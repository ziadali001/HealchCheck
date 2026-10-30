# EMICOOL OCI health-report automation

This repository generates the EMICOOL OCI health report through GitHub Actions.
The workflow runs the existing `oci_health_check.py` with only the `EMICOOL`
OCI profile, creates both HTML and JSON reports, and sends them to the test
recipient only. It does not send reports to an EMICOOL customer address.

## When it runs

The report runs every day at **07:00 Cairo time** (Africa/Cairo, DST-aware)
and is emailed as soon as it has been generated.

GitHub does not guarantee the start time of scheduled runs and has started
this workflow several hours late. For an on-time 07:00 start, also set up the
external trigger below: it starts the workflow through the GitHub API with
`scheduled_delivery=true`, and the GitHub schedule then skips that day so the
report is never emailed twice.

It can also be started from the **Actions** tab with **Run workflow**; tick
**send_email** or **scheduled_delivery** to email the report. Each run
uploads the generated files as an artifact named
`emicool-oci-health-report-<run number>` and retains it for 30 days.

### Setting up the 07:00 trigger (cron-job.org)

1. Create a GitHub fine-grained personal access token: **Settings > Developer
   settings > Fine-grained tokens > Generate new token**. Limit it to this
   repository only, with **Repository permissions > Actions: Read and write**.
   Set an expiry date and note when it must be renewed.
2. At [cron-job.org](https://cron-job.org), create a cron job:
   - **URL:** `https://api.github.com/repos/ziadali001/HealchCheck/actions/workflows/emicool-health-report.yml/dispatches`
   - **Schedule:** every day at 07:00, time zone **Africa/Cairo**
   - **Advanced > Request method:** `POST`
   - **Advanced > Headers:**
     - `Authorization: Bearer <token>`
     - `Accept: application/vnd.github+json`
     - `X-GitHub-Api-Version: 2022-11-28`
     - `Content-Type: application/json`
   - **Advanced > Request body:**
     `{"ref":"main","inputs":{"scheduled_delivery":"true"}}`
3. Use **Test run**: GitHub answers `204 No Content`, and a run named
   **EMICOOL daily 07:00 delivery** appears in the **Actions** tab.

Any other scheduler that can send this POST request at 07:00 Cairo (Azure
Logic Apps, Power Automate, a server cron job) works the same way.

## Required GitHub Actions secrets

In the repository, open **Settings > Secrets and variables > Actions** and add
these repository secrets:

| Secret | Value |
| --- | --- |
| `OCI_EMICOOL_TENANCY_OCID` | EMICOOL OCI tenancy OCID |
| `OCI_EMICOOL_USER_OCID` | OCID of the OCI user that owns the API signing key |
| `OCI_EMICOOL_FINGERPRINT` | OCI API signing-key fingerprint for that user |
| `OCI_EMICOOL_REGION` | Home/default OCI region, for example `me-jeddah-1` |
| `OCI_EMICOOL_PRIVATE_KEY` | Complete private-key PEM, including the `BEGIN` and `END` lines |
| `OCI_EMICOOL_PRIVATE_KEY_PASSPHRASE` | Optional passphrase, only if the private key is encrypted |

## Test-email configuration

Successful reports are emailed from `ziad.cee@gmail.com` to
`zma.cee@gmail.com` as a ZainTech-branded HTML email with the
subject `EMICOOL | OCI Daily Health Report | <date> | <status>`. The HTML and
JSON reports are attached as one zip. There are no customer
recipients in the workflow.

Configure the following before the first run:

| GitHub Actions configuration | Name | Value |
| --- | --- | --- |
| Repository secret | `EMICOOL_REPORT_SMTP_HOST` | `smtp.gmail.com` |
| Repository secret | `EMICOOL_REPORT_SMTP_PORT` | `587` |
| Repository secret | `EMICOOL_REPORT_SMTP_USERNAME` | `ziad.cee@gmail.com` |
| Repository secret | `EMICOOL_REPORT_SMTP_PASSWORD` | Gmail app password for `ziad.cee@gmail.com` |

Enable 2-Step Verification on `ziad.cee@gmail.com`, create a Gmail **App
Password**, then replace the value of `EMICOOL_REPORT_SMTP_PASSWORD` in
**Settings > Secrets and variables > Actions > Secrets**. The workflow uses
Gmail SMTP with STARTTLS (`smtp.gmail.com` on port `587`); no Gmail credential
is stored in this repository.

Use an API signing key for a dedicated automation user where possible. Give the
user only the read permissions necessary for the OCI resources included in the
report.

The workflow creates a temporary OCI config with a single `[EMICOOL]` profile,
uses it for the report run, then removes the temporary key and config. Never
commit an OCI config or PEM key to this repository.

## Report access

After a run completes, the test email is sent only after report generation
succeeds. You can also open that run from the **Actions** tab and download the
report artifact from its **Artifacts** section. This keeps a GitHub copy of
every report for 30 days.
