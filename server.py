import os
import time
from datetime import datetime

import requests
import urllib3
from dotenv import load_dotenv
from fastmcp import FastMCP


# ---------------------------------------------------------
# Load configuration
# ---------------------------------------------------------

load_dotenv()

VIYA_BASE_URL = os.getenv("VIYA_BASE_URL", "").rstrip("/")
VIYA_USERNAME = os.getenv("VIYA_USERNAME")
VIYA_PASSWORD = os.getenv("VIYA_PASSWORD")

JOB_DEFINITION_URI = (
    "/jobDefinitions/definitions/"
    "fee08266-7c91-4621-8b13-2fb4cdb5a5cf"
)

VERIFY_SSL = (
    os.getenv("VIYA_VERIFY_SSL", "false")
    .strip()
    .lower()
    in {"true", "1", "yes"}
)

if not VERIFY_SSL:
    urllib3.disable_warnings(
        urllib3.exceptions.InsecureRequestWarning
    )


# ---------------------------------------------------------
# Create the MCP server
# ---------------------------------------------------------

mcp = FastMCP("Energy Demand Forecast Demo")


# ---------------------------------------------------------
# Validate environment configuration
# ---------------------------------------------------------

def validate_configuration() -> None:
    """Confirm that the required environment variables exist."""

    missing = []

    if not VIYA_BASE_URL:
        missing.append("VIYA_BASE_URL")

    if not VIYA_USERNAME:
        missing.append("VIYA_USERNAME")

    if not VIYA_PASSWORD:
        missing.append("VIYA_PASSWORD")

    if missing:
        raise RuntimeError(
            "Missing environment variables: "
            + ", ".join(missing)
        )


# ---------------------------------------------------------
# Obtain a SAS Viya access token
# ---------------------------------------------------------

def get_viya_token() -> str:
    """Authenticate to SAS Viya and return an access token."""

    validate_configuration()

    token_url = f"{VIYA_BASE_URL}/SASLogon/oauth/token"

    response = requests.post(
        token_url,
        auth=("sas.ec", ""),
        data={
            "grant_type": "password",
            "username": VIYA_USERNAME,
            "password": VIYA_PASSWORD,
        },
        headers={
            "Accept": "application/json",
        },
        verify=VERIFY_SSL,
        timeout=60,
    )

    if not response.ok:
        raise RuntimeError(
            "SAS Viya authentication failed. "
            f"HTTP {response.status_code}: "
            f"{response.text[:1000]}"
        )

    token_data = response.json()
    access_token = token_data.get("access_token")

    if not access_token:
        raise RuntimeError(
            "SAS Viya returned no access token."
        )

    return access_token


# ---------------------------------------------------------
# Build authorization headers
# ---------------------------------------------------------

def get_headers(access_token: str) -> dict:
    """Create the headers used for SAS Viya API calls."""

    return {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json",
        "Content-Type": (
            "application/vnd.sas.job.execution."
            "job.request+json"
        ),
    }


# ---------------------------------------------------------
# Read the job status
# ---------------------------------------------------------

def get_job_status(
    access_token: str,
    job_uri: str,
) -> dict:
    """Retrieve the current state of a submitted SAS job."""

    response = requests.get(
        f"{VIYA_BASE_URL}{job_uri}",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
        },
        verify=VERIFY_SSL,
        timeout=60,
    )

    if not response.ok:
        raise RuntimeError(
            "Unable to retrieve the SAS job status. "
            f"HTTP {response.status_code}: "
            f"{response.text[:1000]}"
        )

    return response.json()


# ---------------------------------------------------------
# MCP tool: test SAS Viya authentication
# ---------------------------------------------------------

@mcp.tool
def test_viya_authentication() -> dict:
    """Test whether the MCP server can authenticate to SAS Viya."""

    try:
        get_viya_token()

        return {
            "status": "success",
            "message": "Authentication to SAS Viya succeeded.",
            "viya_base_url": VIYA_BASE_URL,
        }

    except Exception as exc:
        return {
            "status": "error",
            "message": str(exc),
        }


# ---------------------------------------------------------
# MCP tool: run the energy-demand scenario
# ---------------------------------------------------------

@mcp.tool
def run_energy_demand_scenario(
    start_date: str,
    end_date: str,
    percentage_change: float,
) -> dict:
    """
    Run the SAS energy-demand what-if Job Definition.

    Dates must use YYYY-MM-DD.

    A positive percentage increases the forecast.
    A negative percentage decreases the forecast.
    """

    # Validate the date values before calling SAS Viya

    try:
        start_value = datetime.strptime(
            start_date,
            "%Y-%m-%d",
        ).date()

        end_value = datetime.strptime(
            end_date,
            "%Y-%m-%d",
        ).date()

    except ValueError:
        return {
            "status": "error",
            "message": (
                "Dates must use YYYY-MM-DD. "
                "Example: 2017-09-07."
            ),
        }

    if start_value > end_value:
        return {
            "status": "error",
            "message": (
                "The start date cannot be later "
                "than the end date."
            ),
        }

    if percentage_change < -100 or percentage_change > 100:
        return {
            "status": "error",
            "message": (
                "percentage_change must be between "
                "-100 and 100."
            ),
        }

    try:
        access_token = get_viya_token()

        execution_url = (
            f"{VIYA_BASE_URL}/jobExecution/jobs"
        )

        payload = {
            "name": "Energy Demand Forecast What-If",
            "description": (
                "Scenario submitted from the "
                "Energy Demand Forecast MCP server."
            ),
            "jobDefinitionUri": JOB_DEFINITION_URI,
            "arguments": {
                "_contextName": (
                    "SAS Studio compute context"
                ),
                "_action": "execute",
                "input_table": (
                    "PUBLIC.MW_FINAL_FORECAST"
                ),
                "output_library": "PUBLIC",
                "output_table": (
                    "MW_FINAL_FORECAST_SCENARIO"
                ),
                "start_date": start_date,
                "end_date": end_date,
                "percentage_change": str(
                    percentage_change
                ),
            },
        }

        response = requests.post(
            execution_url,
            headers=get_headers(access_token),
            json=payload,
            verify=VERIFY_SSL,
            timeout=60,
        )

        if not response.ok:
            return {
                "status": "error",
                "stage": "job_submission",
                "http_status": response.status_code,
                "message": response.text[:2000],
            }

        submitted_job = response.json()

        job_uri = (
            submitted_job.get("uri")
            or submitted_job.get("id")
        )

        if job_uri and not job_uri.startswith("/"):
            job_uri = f"/jobExecution/jobs/{job_uri}"

        if not job_uri:
            return {
                "status": "submitted",
                "message": (
                    "The job submission was accepted, "
                    "but no job URI was returned."
                ),
                "submission": submitted_job,
            }

        # Poll SAS Viya until the job reaches a final state

        terminal_states = {
            "completed",
            "success",
            "succeeded",
            "failed",
            "error",
            "canceled",
            "cancelled",
        }

        latest_job = submitted_job
        final_state = "unknown"

        for _ in range(60):
            latest_job = get_job_status(
                access_token,
                job_uri,
            )

            final_state = str(
                latest_job.get("state")
                or latest_job.get("status")
                or latest_job.get("jobState")
                or "unknown"
            ).lower()

            if final_state in terminal_states:
                break

            time.sleep(2)

        successful_states = {
            "completed",
            "success",
            "succeeded",
        }

        if final_state in successful_states:
            return {
                "status": "success",
                "message": (
                    "The energy-demand scenario "
                    "completed successfully."
                ),
                "job_state": final_state,
                "job_uri": job_uri,
                "parameters": {
                    "start_date": start_date,
                    "end_date": end_date,
                    "percentage_change": (
                        percentage_change
                    ),
                },
                "output_table": (
                    "PUBLIC."
                    "MW_FINAL_FORECAST_SCENARIO"
                ),
            }

        if final_state in {
            "failed",
            "error",
            "canceled",
            "cancelled",
        }:
            return {
                "status": "error",
                "message": (
                    "The SAS Job Definition did "
                    "not complete successfully."
                ),
                "job_state": final_state,
                "job_uri": job_uri,
                "job": latest_job,
            }

        return {
            "status": "timeout",
            "message": (
                "The job was submitted, but did not "
                "reach a terminal state within "
                "120 seconds."
            ),
            "job_state": final_state,
            "job_uri": job_uri,
        }

    except Exception as exc:
        return {
            "status": "error",
            "message": str(exc),
        }


# ---------------------------------------------------------
# Run the local MCP server with STDIO
# ---------------------------------------------------------

if __name__ == "__main__":
    mcp.run()
