# EMICOOL OCI health-report automation

This repository generates the EMICOOL OCI health report through GitHub Actions.
The workflow runs the existing `oci_health_check.py` with only the `EMICOOL`
OCI profile and creates both HTML and JSON reports.

## When it runs

The **Generate EMICOOL OCI health report** workflow runs every day at 06:00 UTC
and can also be started from the **Actions** tab with **Run workflow**. Each run
uploads the generated files as an artifact named
`emicool-oci-health-report-<run number>` and retains it for 30 days.

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

Use an API signing key for a dedicated automation user where possible. Give the
user only the read permissions necessary for the OCI resources included in the
report.

The workflow creates a temporary OCI config with a single `[EMICOOL]` profile,
uses it for the report run, then removes the temporary key and config. Never
commit an OCI config or PEM key to this repository.

## Report access

After a run completes, open that run from the **Actions** tab and download the
artifact from its **Artifacts** section. The workflow does not email or publish
the reports outside GitHub.
