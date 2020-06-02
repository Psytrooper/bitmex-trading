import boto3
import sys
import traceback2


class AwsSnsBoto3:
    def __init__(self, profile_name, logger, topic):
        self.topic = topic
        self.logger = logger

        self.sns = None
        # try:
        #     self.sns = boto3.session.Session(profile_name=profile_name).client('sns')
        # except Exception as e:
        #     self.logger.warning(e)
        #     self.logger.error(traceback2.format_exc())

    def notify(self, message, subject):
        if self.sns is not None:
            try:
                self.sns.publish(TopicArn=self.topic, Message=message, Subject=subject)
            except Exception as e:
                self.logger.warning(e)
                self.logger.error(traceback2.format_exc())
        else:
            self.logger.info(f"msg: {message} subject: {subject}")
