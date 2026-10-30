# sas-energy-demand-mcp-demo
SAS Viya energy-demand what-if forecasting demo using FastMCP and SAS Job Execution.

Energy Demand Forecasting with SAS Viya and MCP
This project demonstrates how a FastMCP server can invoke a governed SAS Viya Job Definition to run an energy-demand what-if scenario.

Overview
The MCP tool accepts:

Start date
End date
Percentage forecast change
The SAS Job Definition:

Reads the original forecast table.
Applies the requested percentage change within the selected date range.
Preserves the original forecast values.
Creates scenario forecast variables.
Promotes the output table in CAS.
Scenario output variables
SCENARIO_PREDICT
SCENARIO_LOWER
SCENARIO_UPPER
SCENARIO_ERROR
SCENARIO_APPLIED
Prerequisites
SAS Viya
Access to SAS Job Execution
Access to a writable CAS library
Python 3
FastMCP
Node.js, npm, and npx for MCP Inspector
Installation
Create and activate a virtual environment:

py -m venv .venv
.\.venv\Scripts\Activate.ps1

