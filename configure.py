import argparse
from typing import Any
import requests
import io
import json

from oauth2client.service_account import ServiceAccountCredentials


PROJECT_ID = 'fir-config-sample-cfe54'
BASE_URL = 'https://firebaseremoteconfig.googleapis.com'
REMOTE_CONFIG_ENDPOINT = 'v1/projects/' + PROJECT_ID + '/remoteConfig'
REMOTE_CONFIG_URL = BASE_URL + '/' + REMOTE_CONFIG_ENDPOINT
SCOPES = ['https://www.googleapis.com/auth/firebase.remoteconfig']

# [START retrieve_access_token]
def _get_access_token():
  """Retrieve a valid access token that can be used to authorize requests.

  :return: Access token.
  """
  credentials = ServiceAccountCredentials.from_json_keyfile_name(
      'service-account.json', SCOPES)
  access_token_info = credentials.get_access_token()
  return access_token_info.access_token
# [END retrieve_access_token]

def _load_template() -> Any:
  template = {}
  try:
    with open("config.json") as stream:
      template = json.load(stream)
    stream.close()
    return template
  except IOError:
    print("config.json file not found.")

def _get_etag():
  headers = {
    'Authorization': 'Bearer ' + _get_access_token()
  }
  resp = requests.get(REMOTE_CONFIG_URL, headers=headers)
  return resp.headers['ETag']

def _get():
  """Retrieve the current Firebase Remote Config template from server.

  Retrieve the current Firebase Remote Config template from server and store it
  locally.
  """
  headers = {
    'Authorization': 'Bearer ' + _get_access_token()
  }
  resp = requests.get(REMOTE_CONFIG_URL, headers=headers)

  if resp.status_code == 200:
    with io.open('config.json', 'wb') as f:
      f.write(resp.text.encode('utf-8'))

    print('Retrieved template has been written to config.json')
    print('ETag from server: {}'.format(resp.headers['ETag']))
  else:
    print('Unable to get template')
    print(resp.text)

def _listVersions():
  """Print the last 5 Remote Config version's metadata."""
  headers = {
    'Authorization': 'Bearer ' + _get_access_token()
  }
  resp = requests.get(REMOTE_CONFIG_URL + ':listVersions?pageSize=5', headers=headers)

  if resp.status_code == 200:
    print('Versions:')
    print(resp.text)
  else:
    print('Request to print template versions failed.')
    print(resp.text)

def _rollback(version):
  """Roll back to an available version of Firebase Remote Config template.

  :param version: The version of the template to roll back to.
  """
  headers = {
    'Authorization': 'Bearer ' + _get_access_token()
  }

  json = {
    "version_number": version
  }
  resp = requests.post(REMOTE_CONFIG_URL + ':rollback', headers=headers, json=json)

  if resp.status_code == 200:
    print('Rolled back to version: ' + version)
    print(resp.text)
    print('ETag from server: {}'.format(resp.headers['ETag']))
  else:
    print('Request to roll back to version ' + version + ' failed.')
    print(resp.text)

def _publish():
  """Publish local template to Firebase server.

  Args:
    etag: ETag for safe (avoid race conditions) template updates.
        * can be used to force template replacement.
  """
  # get latest etag
  etag = _get_etag()
  with open('config.json', 'r', encoding='utf-8') as f:
    content = f.read()
  headers = {
    'Authorization': 'Bearer ' + _get_access_token(),
    'Content-Type': 'application/json; UTF-8',
    'If-Match': etag
  }
  resp = requests.put(REMOTE_CONFIG_URL, data=content.encode('utf-8'), headers=headers)
  if resp.status_code == 200:
    print('Template has been published.')
    print('ETag from server: {}'.format(resp.headers['ETag']))
  else:
    print('Unable to publish template.')
    print(resp.text)

def _update_parameter(args):
  try:
    template = _load_template()

    if not args.old_param in template['parameters'].keys():
      raise ValueError
    
    print(template["parameters"])
    template['parameters'][args.new_param] = template['parameters'].pop(args.old_param)
    print(template["parameters"])
  except IOError:
    print("config.json file not found.")
  except ValueError:
    print(f"The {args.old_param} parameter is not found.")

def _update_condition(args):
  valid_condition_keys = set(["name", "expression", "tagColor"])
  try:
    template = _load_template()
    value = args.condition
    deserialize_value = json.loads(f"{value}")
    if not set(deserialize_value.keys()).issubset(valid_condition_keys):
      raise ValueError

    if [ob for ob in template["conditions"] if ob == value]:
      print("No need to update")
    # check if condition exists in config.json
    elif deserialize_value["name"] in [value["name"] for value in template["conditions"]]:

      print("Updating...")
      # template["conditions"] = {**template["conditions"][]}
      print(deserialize_value["name"])
    else:
      print("Creating...")
      template["conditions"].append(f"{value}")

  except ValueError:
    print("Invalid keys in condition.")
  except Exception as e:
    print(e)


def main():
  parser = argparse.ArgumentParser()
  parser.add_argument('--action')
  parser.add_argument('--etag')
  parser.add_argument('--version')

  sub_parsers = parser.add_subparsers()

  # add sub command to update parameter
  update_parameter = sub_parsers.add_parser("update-parameter", help="update parameters")
  update_parameter.add_argument("--old-param", help="old parameter name that exists", required=True)
  update_parameter.add_argument("--new-param", help="new parameter name", required=True)
  update_parameter.set_defaults(func=_update_parameter)

  update_condition = sub_parsers.add_parser("update-condition", help="update conditions")
  update_condition.add_argument("--condition", required=True, help="condition in json format")
  update_condition.set_defaults(func=_update_condition)

  args = parser.parse_args()

  if "func" in args:
    args.func(args)

  if args.action and args.action == 'get':
    _get()
  elif args.action and args.action == 'publish':
    _publish()
  elif args.action and args.action == 'versions':
    _listVersions()
  elif args.action and args.action == 'rollback' and args.version:
    _rollback(args.version)
  else:
    print(
      '''
      Invalid command. Please use one of the following commands:
      python configure.py --action=get
      python configure.py --action=publish
      python configure.py --action=versions
      python configure.py --action=rollback --version=<TEMPLATE_VERSION_NUMBER>
      '''
    )

if __name__ == '__main__':
  main()