// Pipeline: Checkout -> SonarQube scan -> Quality Gate -> Hadoop -> Result Display

pipeline {

  agent {
    kubernetes {
      yaml '''
        apiVersion: v1
        kind: Pod
        spec:
          containers:
          - name: gcloud
            image: google/cloud-sdk:slim
            command: [sleep, infinity]
            volumeMounts:
            - name: gcp-sa-key
              mountPath: /var/secrets/google
              readOnly: true
            - name: sonar-token
              mountPath: /var/secrets/sonar
              readOnly: true
          volumes:
          - name: gcp-sa-key
            secret:
              secretName: gcp-sa-key
          - name: sonar-token
            secret:
              secretName: sonar-token
      '''
      defaultContainer 'gcloud'
    }
  }

  environment {
    SONAR_PROJECT              = "14848-sonar"
    GCP_PROJECT                = "courseproject-488619"
    GCP_REGION                 = "us-central1"
    DATAPROC_CLUSTER           = "hadoop-cluster-master"
    GCS_BUCKET                 = "gs://14848-hadoop-results"
    MAYAVI_REPO                = "https://github.com/GodZmk/mayavi.git"
    GOOGLE_APPLICATION_CREDENTIALS = "/var/secrets/google/sa-key.json"
  }

  stages {

    stage('Checkout') {
      steps {
        git url: "${MAYAVI_REPO}", branch: 'main'
      }
    }

    stage('SonarQube Analysis') {
      steps {
        withSonarQubeEnv('SonarQube') {
          sh '''
            SONAR_TOKEN_VAL=$(cat /var/secrets/sonar/token)

            # Pre-assign custom quality gate (no-op if project doesn't exist yet)
            curl -sf -u "${SONAR_TOKEN_VAL}:" -X POST \
              "${SONAR_HOST_URL}/api/qualitygates/select?gateName=14848-blocker-gate&projectKey=${SONAR_PROJECT}" || true

            # Install sonar-scanner if not present
            if [ ! -f /opt/sonar-scanner/bin/sonar-scanner ]; then
              apt-get update -qq && apt-get install -y -qq unzip wget
              wget -q https://binaries.sonarsource.com/Distribution/sonar-scanner-cli/sonar-scanner-cli-5.0.1.3006-linux.zip -O /tmp/sonar.zip
              unzip -q /tmp/sonar.zip -d /opt/
              mv /opt/sonar-scanner-*-linux /opt/sonar-scanner && rm /tmp/sonar.zip
            fi

            # Run analysis on Python files
            /opt/sonar-scanner/bin/sonar-scanner \
              -Dsonar.projectKey="${SONAR_PROJECT}" \
              -Dsonar.sources=. \
              -Dsonar.inclusions="**/*.py" \
              -Dsonar.exclusions="**/docs/**,**/examples/**,**/test_*.py,**/.git/**,**/plugins/**,tvtk/tools/**,mayavi/core/registry.py" \
              -Dsonar.python.version=3 \
              -Dsonar.host.url="${SONAR_HOST_URL}" \
              -Dsonar.login="${SONAR_AUTH_TOKEN}" \
              -Dsonar.scm.disabled=true

            # Post-assign quality gate (handles newly created projects)
            curl -sf -u "${SONAR_TOKEN_VAL}:" -X POST \
              "${SONAR_HOST_URL}/api/qualitygates/select?gateName=14848-blocker-gate&projectKey=${SONAR_PROJECT}" || true
          '''
        }
      }
    }

    stage('Quality Gate') {
      steps {
        script {
          sh '''
            SONAR_TOKEN_VAL=$(cat /var/secrets/sonar/token)
            CE_TASK_ID=$(grep "^ceTaskId=" .scannerwork/report-task.txt | cut -d= -f2)
            SONAR_HOST=$(grep "^serverUrl=" .scannerwork/report-task.txt | cut -d= -f2-)

            # Poll CE task until complete (max 10 min)
            for i in $(seq 1 120); do
              TASK_STATUS=$(curl -sf -u "${SONAR_TOKEN_VAL}:" \
                "${SONAR_HOST}/api/ce/task?id=${CE_TASK_ID}" \
                | grep -o '"status":"[^"]*"' | head -1 | cut -d'"' -f4)
              echo "[${i}/120] CE status: ${TASK_STATUS}"
              [ "$TASK_STATUS" = "SUCCESS" ] && break
              if [ "$TASK_STATUS" = "FAILED" ] || [ "$TASK_STATUS" = "CANCELLED" ]; then exit 1; fi
              sleep 5
            done
            if [ "$TASK_STATUS" != "SUCCESS" ]; then echo "Timeout." && exit 1; fi

            # Check quality gate result
            QG_STATUS=$(curl -sf -u "${SONAR_TOKEN_VAL}:" \
              "${SONAR_HOST}/api/qualitygates/project_status?projectKey=${SONAR_PROJECT}" \
              | grep -o '"status":"[^"]*"' | head -1 | cut -d'"' -f4)
            echo "Quality Gate: ${QG_STATUS}"
            if [ "$QG_STATUS" != "OK" ]; then
              echo "BLOCKER issues found — aborting."
              exit 1
            fi
          '''
        }
      }
    }

    stage('Submit Hadoop Job') {
      steps {
        script {
          sh '''
            gcloud auth activate-service-account --key-file="${GOOGLE_APPLICATION_CREDENTIALS}" --quiet
            gcloud config set project "${GCP_PROJECT}" --quiet
          '''

          sh """
            gsutil cp hadoop/mapper.py  ${GCS_BUCKET}/scripts/mapper.py
            gsutil cp hadoop/reducer.py ${GCS_BUCKET}/scripts/reducer.py
            gsutil -m rm -rf ${GCS_BUCKET}/input/ 2>/dev/null || true
            gsutil -m rsync -r -x '\\.git/.*|\\.pyc\$|\\.egg-info/.*|__pycache__/.*' . ${GCS_BUCKET}/input/mayavi/
          """

          def ts = sh(script: "date -u +%Y%m%d-%H%M%S", returnStdout: true).trim()
          env.OUTPUT_PATH = "${GCS_BUCKET}/output/${ts}"

          env.DATAPROC_JOB_ID = sh(
            script: """
              gcloud dataproc jobs submit hadoop \
                --cluster="${DATAPROC_CLUSTER}" --region="${GCP_REGION}" --project="${GCP_PROJECT}" \
                --jar=file:///usr/lib/hadoop/hadoop-streaming.jar \
                --async --format='value(reference.jobId)' \
                -- \
                -D mapreduce.input.fileinputformat.input.dir.recursive=true \
                -files "${GCS_BUCKET}/scripts/mapper.py,${GCS_BUCKET}/scripts/reducer.py" \
                -mapper "python3 mapper.py" -reducer "python3 reducer.py" \
                -input "${GCS_BUCKET}/input/mayavi" -output "${env.OUTPUT_PATH}"
            """,
            returnStdout: true
          ).trim()
          echo "Submitted Dataproc job: ${env.DATAPROC_JOB_ID}"
        }
      }
    }

    stage('Display Results') {
      steps {
        sh '''
          gcloud dataproc jobs wait "${DATAPROC_JOB_ID}" --region="${GCP_REGION}" --project="${GCP_PROJECT}"
          echo "=== Hadoop Line Count Results ==="
          gsutil cat "${OUTPUT_PATH}/part-*" | sort | tee hadoop-results.txt
        '''
        archiveArtifacts artifacts: 'hadoop-results.txt', fingerprint: true
      }
    }

  }

  post {
    failure { echo "Pipeline FAILED." }
    success { echo "Pipeline SUCCESS. Results: ${OUTPUT_PATH}" }
  }

}
