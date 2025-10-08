import smtplib
import secrets
from datetime import datetime, timezone, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional
import logging

from app.core.config import settings
from app.models.user import User
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


class EmailService:
    """邮件服务类，处理密码重置邮件"""
    
    def __init__(self):
        self.smtp_host = settings.SMTP_HOST
        self.smtp_port = settings.SMTP_PORT
        self.smtp_user = settings.SMTP_USER
        self.smtp_password = settings.SMTP_PASSWORD
        self.smtp_use_tls = settings.SMTP_USE_TLS
        self.from_name = settings.EMAIL_FROM_NAME
        self.from_address = settings.email_from_address
    
    def _get_smtp_connection(self):
        """获取SMTP连接"""
        try:
            server = smtplib.SMTP(self.smtp_host, self.smtp_port)
            if self.smtp_use_tls:
                server.starttls()
            if self.smtp_user and self.smtp_password:
                server.login(self.smtp_user, self.smtp_password)
            return server
        except Exception as e:
            logger.error(f"Failed to connect to SMTP server: {e}")
            raise
    
    def _send_email(self, to_email: str, subject: str, html_content: str, text_content: str = None) -> bool:
        """发送邮件的通用方法"""
        try:
            # 如果邮件服务未配置，则记录到控制台（开发环境）
            if not self.smtp_user or not self.smtp_password:
                logger.info(f"""
                ===========================================
                📧 EMAIL (Development Mode)
                ===========================================
                To: {to_email}
                Subject: {subject}
                
                {text_content or html_content}
                ===========================================
                """)
                return True
            
            # 创建邮件
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = f"{self.from_name} <{self.from_address}>"
            msg['To'] = to_email
            
            # 添加文本内容
            if text_content:
                text_part = MIMEText(text_content, 'plain', 'utf-8')
                msg.attach(text_part)
            
            # 添加HTML内容
            html_part = MIMEText(html_content, 'html', 'utf-8')
            msg.attach(html_part)
            
            # 发送邮件
            with self._get_smtp_connection() as server:
                server.send_message(msg)
            
            logger.info(f"Email sent successfully to {to_email}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send email to {to_email}: {e}")
            return False
    
    def generate_verification_token(self) -> str:
        """生成安全的验证令牌"""
        return secrets.token_urlsafe(32)
    
    def send_password_reset_email(self, user: User, db: Session) -> bool:
        """发送密码重置邮件"""
        try:
            # 检查是否可以发送重置邮件
            if not user.can_request_password_reset():
                logger.warning(f"Password reset request denied for {user.email} - rate limited")
                return False
            
            # 生成重置令牌
            token = self.generate_verification_token()
            
            # 更新用户重置信息
            user.password_reset_token = token
            user.password_reset_sent_at = datetime.now(timezone.utc)
            db.commit()
            
            # 生成重置链接
            reset_url = settings.get_frontend_password_reset_url(token)
            
            # 邮件内容
            subject = f"Reset your {settings.EMAIL_FROM_NAME} password"
            
            # HTML邮件模板
            html_content = self._get_password_reset_email_html(user, reset_url)
            
            # 纯文本内容（备用）
            text_content = f"""
Password Reset Request for {settings.EMAIL_FROM_NAME}

Hi {user.full_name or user.email},

We received a request to reset your password. Click the link below to set a new password:

{reset_url}

This link will expire in {settings.PASSWORD_RESET_EXPIRE_HOURS} hour(s).

If you didn't request this password reset, you can safely ignore this email. Your password will remain unchanged.

For security reasons, this link can only be used once.

Best regards,
The {settings.EMAIL_FROM_NAME} Team
            """.strip()
            
            return self._send_email(user.email, subject, html_content, text_content)
            
        except Exception as e:
            logger.error(f"Failed to send password reset email to {user.email}: {e}")
            return False
    
    def _get_password_reset_email_html(self, user: User, reset_url: str) -> str:
        """获取密码重置的HTML模板"""
        return f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Reset Your Password</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            line-height: 1.6;
            color: #333;
            max-width: 600px;
            margin: 0 auto;
            padding: 20px;
        }}
        .header {{
            text-align: center;
            padding: 20px 0;
            border-bottom: 2px solid #E88B00;
        }}
        .logo {{
            width: 60px;
            height: 60px;
            background: #E88B00;
            border-radius: 12px;
            margin: 0 auto 16px;
            display: flex;
            align-items: center;
            justify-content: center;
            color: white;
            font-size: 24px;
            font-weight: bold;
        }}
        .content {{
            padding: 30px 0;
        }}
        .button {{
            display: inline-block;
            background: #E88B00;
            color: white;
            padding: 12px 30px;
            text-decoration: none;
            border-radius: 6px;
            font-weight: 600;
            margin: 20px 0;
        }}
        .footer {{
            color: #666;
            font-size: 14px;
            border-top: 1px solid #eee;
            padding-top: 20px;
            margin-top: 30px;
        }}
        .warning {{
            background: #fff3cd;
            border-left: 4px solid #ffc107;
            padding: 15px;
            margin: 20px 0;
        }}
        .security-notice {{
            background: #f8f9fa;
            border-left: 4px solid #6c757d;
            padding: 15px;
            margin: 20px 0;
        }}
    </style>
</head>
<body>
    <div class="header">
        <div class="logo">⚡</div>
        <h1 style="margin: 0; color: #E88B00;">{settings.EMAIL_FROM_NAME}</h1>
    </div>
    
    <div class="content">
        <h2>Password Reset Request</h2>
        
        <p>Hi {user.full_name or user.email},</p>
        
        <p>We received a request to reset your password for your {settings.EMAIL_FROM_NAME} account. Click the button below to set a new password:</p>
        
        <div style="text-align: center;">
            <a href="{reset_url}" class="button">Reset Password</a>
        </div>
        
        <p>Or copy and paste this link into your browser:</p>
        <p style="word-break: break-all; color: #666; font-size: 14px;">{reset_url}</p>
        
        <div class="warning">
            <strong>⏰ Time Sensitive:</strong> This password reset link will expire in {settings.PASSWORD_RESET_EXPIRE_HOURS} hour(s).
        </div>
        
        <div class="security-notice">
            <strong>🔒 Security Notice:</strong>
            <ul style="margin: 10px 0;">
                <li>This link can only be used once</li>
                <li>If you didn't request this reset, your password remains secure</li>
                <li>Always use a strong, unique password</li>
            </ul>
        </div>
    </div>
    
    <div class="footer">
        <p><strong>Didn't request this password reset?</strong> You can safely ignore this email. Your password will remain unchanged.</p>
        <p>For security questions, contact us at support@fintellic.com</p>
    </div>
</body>
</html>
        """
    
    def send_password_changed_notification(self, user: User) -> bool:
        """发送密码修改成功通知邮件"""
        try:
            subject = f"Your {settings.EMAIL_FROM_NAME} password has been changed"
            
            text_content = f"""
Password Changed Successfully

Hi {user.full_name or user.email},

This email confirms that your password for {settings.EMAIL_FROM_NAME} was successfully changed.

Time: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}

If you did not make this change, please contact our support team immediately at support@fintellic.com.

Best regards,
The {settings.EMAIL_FROM_NAME} Team
            """.strip()
            
            html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Password Changed</title>
</head>
<body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
    <h2 style="color: #28a745;">Password Changed Successfully</h2>
    
    <p>Hi {user.full_name or user.email},</p>
    
    <p>This email confirms that your password for {settings.EMAIL_FROM_NAME} was successfully changed.</p>
    
    <p><strong>Time:</strong> {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}</p>
    
    <div style="background: #f8f9fa; border-left: 4px solid #dc3545; padding: 15px; margin: 20px 0;">
        <strong>⚠️ Didn't make this change?</strong><br>
        If you did not change your password, please contact our support team immediately at support@fintellic.com.
    </div>
    
    <p>Best regards,<br>The {settings.EMAIL_FROM_NAME} Team</p>
</body>
</html>
            """
            
            return self._send_email(user.email, subject, html_content, text_content)
            
        except Exception as e:
            logger.error(f"Failed to send password change notification to {user.email}: {e}")
            return False


# 创建全局邮件服务实例
email_service = EmailService()