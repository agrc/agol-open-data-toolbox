# Stewardship Endpoint Link Updater

This tool updates the open data link for all items in the AGOL_ITEMS meta table by matching the source table name with the destination in the stewardship Google sheet.

## Setup

### Secrets

You will need a `.env` file with the following filled out

```yaml
AGOL_SERVER=
AGOL_DB=
AGOL_USER=
AGOL_PW=
AGOL_SHEET=
```

You will also need a service account named `client_secret.json` with edit access to the Google sheet you are going to update.

### Dependencies

`pip install -r requirements.txt` into a python 3.7 environment

## Usage

run the python file and it will do it's thing e.g., `python main.py`
