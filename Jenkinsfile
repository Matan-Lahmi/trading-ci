pipeline {
    agent { label 'docker-agent' }

    environment {
        DOCKER_USER   = "matanlahmi"
        IMAGE_NAME    = "${env.JOB_NAME.toLowerCase()}"
        IMAGE_TAG     = "${env.BUILD_NUMBER}"
        FULL_IMAGE    = "${DOCKER_USER}/${IMAGE_NAME}:${IMAGE_TAG}"
        LATEST_IMAGE  = "${DOCKER_USER}/${IMAGE_NAME}:latest"
        REGISTRY_CRED = "docker-hub-credentials"
    }

    stages {
        stage('Checkout') {
            steps {
                checkout scm
            }
        }

        stage('Code Quality') {
            parallel {
                stage('Flake8') {
                    steps {
                        sh 'flake8 .'
                    }
                }
                stage('pip-audit') {
                    steps {
                        sh 'pip-audit -r requirements.txt'
                    }
                }
            }
        }

        stage('Tests') {
            steps {
                sh 'pip3 install -r requirements.txt --break-system-packages'
                sh 'python3 -m pytest'
            }
        }

        stage('Docker Build') {
            steps {
                sh "docker build -t ${FULL_IMAGE} ."
                sh "docker tag ${FULL_IMAGE} ${LATEST_IMAGE}"
            }
        }

        stage('Trivy Scan') {
            steps {
                sh "trivy image --cache-dir /tmp/trivy-${IMAGE_NAME} --exit-code 1 --severity HIGH,CRITICAL --ignore-unfixed ${FULL_IMAGE}"
            }
        }

        stage('Push') {
            steps {
                withCredentials([usernamePassword(
                    credentialsId: "${REGISTRY_CRED}",
                    usernameVariable: 'DOCKER_USER_VAR',
                    passwordVariable: 'DOCKER_PASS'
                )]) {
                    sh 'echo "$DOCKER_PASS" | docker login -u "$DOCKER_USER_VAR" --password-stdin'
                    sh "docker push ${FULL_IMAGE}"
                    sh "docker push ${LATEST_IMAGE}"
                }
            }
        }
    }

    post {
        success {
            echo "Pipeline succeeded - ${FULL_IMAGE} pushed to Docker Hub"
        }
        failure {
            echo "Pipeline failed - Build #${BUILD_NUMBER} of ${IMAGE_NAME}"
        }
        always {
            cleanWs()
        }
    }
}
