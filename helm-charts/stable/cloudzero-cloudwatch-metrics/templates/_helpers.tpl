{{/* vim: set filetype=mustache: */}}
{{/*
Expand the name of the chart.
*/}}
{{- define "cloudzero-cloudwatch-metrics.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{/*
Create a default fully qualified app name.
We truncate at 63 chars because some Kubernetes name fields are limited to this (by the DNS naming spec).
If release name contains chart name it will be used as a full name.
*/}}
{{- define "cloudzero-cloudwatch-metrics.fullname" -}}
{{- if .Values.fullnameOverride -}}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- $name := default .Chart.Name .Values.nameOverride -}}
{{- if contains $name .Release.Name -}}
{{- .Release.Name | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}
{{- end -}}

{{/*
Create chart name and version as used by the chart label.
*/}}
{{- define "cloudzero-cloudwatch-metrics.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{/*
Common labels
*/}}
{{- define "cloudzero-cloudwatch-metrics.labels" -}}
helm.sh/chart: {{ include "cloudzero-cloudwatch-metrics.chart" . }}
{{ include "cloudzero-cloudwatch-metrics.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end -}}

{{/*
Selector labels
*/}}
{{- define "cloudzero-cloudwatch-metrics.selectorLabels" -}}
app.kubernetes.io/name: {{ include "cloudzero-cloudwatch-metrics.name" . }}
{{- end -}}

{{/*
Create the name of the service account to use
*/}}
{{- define "cloudzero-cloudwatch-metrics.serviceAccountName" -}}
  {{ default (include "cloudzero-cloudwatch-metrics.fullname" .) .Values.serviceAccount.name }}
{{- end -}}
