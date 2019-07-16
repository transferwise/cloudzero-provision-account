# -*- coding: utf-8 -*-
# Copyright (c) 2016-present, CloudZero, Inc. All rights reserved.
# Licensed under the BSD-style license. See LICENSE file in the project root for full license information.

from pprint import pformat
import boto3
import cfnresponse
from toolz.curried import assoc_in, get_in, keyfilter, merge, pipe, update_in
from voluptuous import Any, ExactSequence, Schema, ALLOW_EXTRA, REMOVE_EXTRA


import logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)


ct = boto3.client('cloudtrail')
cur = boto3.client('cur')
s3 = boto3.client('s3')

DEFAULT_OUTPUT = {
    'IsAuditAccount': False,
    'AuditCloudTrailBucketName': None,
    'IsConnectedAccount': False,
    'IsCloudTrailAccount': False,
    'CloudTrailSNSTopicArn': None,
    'IsMasterPayerAccount': False,
    'MasterPayerBillingBucketName': None,
}


#####################
#
# Boundary Validation
#
#####################
INPUT_SCHEMA = Schema({
    'event': {
        'RequestType': Any('Create', 'Update', 'Delete'),
        'ResourceProperties': {
            'AccountId': str
        },
        'ResponseURL': str,
        'StackId': str
    }
}, required=True, extra=REMOVE_EXTRA)

OUTPUT_SCHEMA = Schema({
    'output': {
        'IsAuditAccount': bool,
        'AuditCloudTrailBucketName': Any(None, str),
        'IsConnectedAccount': bool,
        'IsCloudTrailAccount': bool,
        'CloudTrailSNSTopicArn': Any(None, str),
        'IsMasterPayerAccount': bool,
        'MasterPayerBillingBucketName': Any(None, str),
    },
}, required=True, extra=ALLOW_EXTRA)

event_account_id = get_in(['event', 'ResourceProperties', 'AccountId'])


#####################
#
# Coeffects, i.e. from the outside world
#
#####################
def coeffects(world):
    return pipe(world,
                coeffects_cloudtrail,
                coeffects_s3,
                coeffects_cur)


def coeffect(name):
    def d(f):
        def w(world):
            data = {}
            try:
                data = f(world)
            except Exception:
                logger.warning(f'Failed to get {name} information.', exc_info=True)
            return assoc_in(world, ['coeffects', name], data)
        return w
    return d


@coeffect('cloudtrail')
def coeffects_cloudtrail(world):
    response = ct.describe_trails()
    return keyfilter(lambda x: x in {'trailList'}, response)


@coeffect('s3')
def coeffects_s3(world):
    response = s3.list_buckets()
    return keyfilter(lambda x: x in {'Buckets'}, response)


@coeffect('cur')
def coeffects_cur(world):
    response = cur.describe_report_definitions()
    return keyfilter(lambda x: x in {'ReportDefinitions'}, response)


#####################
#
# Business Logic
#
#####################
def discover_audit_account(world):
    trail_bucket = get_in(['coeffects', 'cloudtrail', 'trailList', 0, 'S3BucketName'], world)
    local_buckets = {x['Name'] for x in get_in(['coeffects', 's3', 'Buckets'], world, [])}
    output = {
        'IsAuditAccount': trail_bucket in local_buckets,
        'AuditCloudTrailBucketName': trail_bucket,
    }
    return update_in(world, ['output'], lambda x: merge(x or {}, output))


def discover_connected_account(world):
    output = {
        'IsConnectedAccount': True,
    }
    return update_in(world, ['output'], lambda x: merge(x or {}, output))


def safe_check(schema, data):
    try:
        return schema(data)
    except Exception:
        logger.debug(f'Data {pformat(data)} did not match schema {schema}', exc_info=True)
        return None


def keep_valid(schema, xs):
    return [
        y for y in [safe_check(schema, x) for x in xs]
        if y is not None
    ]


MINIMUM_CLOUDTRAIL_CONFIGURATION = Schema({
    "S3BucketName": str,
    "SnsTopicName": str,
    "SnsTopicARN": str,
    "IsMultiRegionTrail": True,
    "TrailARN": str,
}, extra=ALLOW_EXTRA, required=True)


IDEAL_CLOUDTRAIL_CONFIGURATION = MINIMUM_CLOUDTRAIL_CONFIGURATION.extend({
    "IsOrganizationTrail": True,
}, extra=ALLOW_EXTRA, required=True)


def get_first_valid_trail(trails):
    return trails[0]['SnsTopicARN'] if trails else None


def discover_cloudtrail_account(world):
    trails = get_in(['coeffects', 'cloudtrail', 'trailList'], world, [])
    valid_trails = keep_valid(IDEAL_CLOUDTRAIL_CONFIGURATION, trails) or keep_valid(MINIMUM_CLOUDTRAIL_CONFIGURATION, trails)
    trail_topic = get_first_valid_trail(valid_trails)
    account_id = trail_topic.split(':')[4] if trail_topic else None
    output = {
        'IsCloudTrailAccount': account_id == event_account_id(world),
        'CloudTrailSNSTopicArn': trail_topic,
    }
    return update_in(world, ['output'], lambda x: merge(x or {}, output))


MINIMUM_BILLING_REPORT = Schema({
    'TimeUnit': 'HOURLY',
    'Format': 'textORcsv',
    'Compression': 'GZIP',
    'AdditionalSchemaElements': ExactSequence(['RESOURCES']),
    'S3Bucket': str,
    'S3Prefix': str,
    'S3Region': str,
    'ReportVersioning': 'CREATE_NEW_REPORT',
    'RefreshClosedReports': True,
}, extra=ALLOW_EXTRA, required=True)


def get_first_valid_report_definition_s3_bucket(valid_report_definitions, default=None):
    return valid_report_definitions[0]['S3Bucket'] if any(valid_report_definitions) else default


def discover_master_payer_account(world):
    report_definitions = get_in(['coeffects', 'cur', 'ReportDefinitions'], world, [])
    local_buckets = {x['Name'] for x in get_in(['coeffects', 's3', 'Buckets'], world, [])}
    valid_report_definitions = keep_valid(MINIMUM_BILLING_REPORT, report_definitions)
    default_s3_bucket = get_first_valid_report_definition_s3_bucket(valid_report_definitions)
    valid_local_report_definitions = [x for x in valid_report_definitions if x['S3Bucket'] in local_buckets]
    local = any(valid_local_report_definitions)
    output = {
        'IsMasterPayerAccount': local,
        'MasterPayerBillingBucketName': get_first_valid_report_definition_s3_bucket(valid_local_report_definitions, default=default_s3_bucket),
    }
    return update_in(world, ['output'], lambda x: merge(x or {}, output))


def discover_account_types(world):
    return pipe(world,
                discover_audit_account,
                discover_connected_account,
                discover_cloudtrail_account,
                discover_master_payer_account)


#####################
#
# Handler
#
#####################
def handler(event, context, **kwargs):
    status = cfnresponse.SUCCESS
    world = {}
    try:
        logger.info(f'Processing event {pformat(event)}')
        world = pipe({'event': event, 'kwargs': kwargs},
                     INPUT_SCHEMA,
                     coeffects,
                     discover_account_types,
                     OUTPUT_SCHEMA)
        logger.info(f'Finished Processing: {pformat(world)}')
    except Exception as err:
        logger.exception(err)
    finally:
        output = world.get('output', DEFAULT_OUTPUT)
        logger.info(f'Sending output {pformat(output)}')
        cfnresponse.send(event, context, status, output, event.get('PhysicalResourceId'))
