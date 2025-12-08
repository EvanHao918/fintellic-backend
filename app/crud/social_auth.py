"""
Social Auth CRUD Methods
========================
这些方法需要添加到 app/crud/user.py 中

使用方式：
1. 将这些方法添加到现有的 crud/user.py 文件
2. 或者导入这个文件使用
"""

from typing import Optional
from datetime import datetime, timezone
from sqlalchemy.orm import Session

from app.models.user import User
from app.core.security import get_password_hash


# ==================== 社交登录查询方法 ====================

def get_user_by_apple_id(db: Session, apple_user_id: str) -> Optional[User]:
    """通过 Apple User ID 查找用户"""
    return db.query(User).filter(User.apple_user_id == apple_user_id).first()


def get_user_by_google_id(db: Session, google_user_id: str) -> Optional[User]:
    """通过 Google User ID 查找用户"""
    return db.query(User).filter(User.google_user_id == google_user_id).first()


def get_user_by_linkedin_id(db: Session, linkedin_user_id: str) -> Optional[User]:
    """通过 LinkedIn User ID 查找用户"""
    return db.query(User).filter(User.linkedin_user_id == linkedin_user_id).first()


def get_user_by_social_id(
    db: Session, 
    provider: str, 
    social_id: str
) -> Optional[User]:
    """
    通过社交账号 ID 查找用户（统一方法）
    
    Args:
        provider: "apple", "google", "linkedin"
        social_id: 对应平台的用户ID
    """
    if provider == "apple":
        return get_user_by_apple_id(db, social_id)
    elif provider == "google":
        return get_user_by_google_id(db, social_id)
    elif provider == "linkedin":
        return get_user_by_linkedin_id(db, social_id)
    return None


# ==================== 社交登录创建/更新方法 ====================

def create_user_from_social(
    db: Session,
    provider: str,
    social_id: str,
    email: Optional[str],
    full_name: Optional[str] = None,
    email_verified: bool = True,
) -> User:
    """
    从社交登录创建新用户
    
    社交登录用户特点：
    1. 没有密码（hashed_password 为空或占位符）
    2. 邮箱已验证（社交平台已验证）
    3. 绑定了社交账号 ID
    """
    # 生成一个随机占位密码（用户无法用此登录）
    import secrets
    placeholder_password = secrets.token_urlsafe(32)
    
    # 生成 username
    username = None
    if full_name:
        # 从全名生成 username (如 "John Doe" -> "john_doe")
        username = full_name.lower().replace(' ', '_')
        # 移除非法字符，只保留字母、数字、下划线
        import re
        username = re.sub(r'[^a-z0-9_]', '', username)
    
    # 如果没有 full_name，从邮箱生成 username
    if not username and email:
        username = email.split('@')[0]
        import re
        username = re.sub(r'[^a-z0-9_]', '', username.lower())
    
    # 确保 username 唯一
    if username:
        from app.crud.user import crud_user
        base_username = username
        counter = 1
        while crud_user.get_by_username(db, username):
            username = f"{base_username}_{counter}"
            counter += 1
    
    user = User(
        email=email,
        full_name=full_name if full_name else "User",
        username=username,
        hashed_password=get_password_hash(placeholder_password),
        is_verified=email_verified,
        tier="FREE",
        registration_source=provider,
        created_at=datetime.now(timezone.utc),
    )
    
    # 设置社交账号 ID
    if provider == "apple":
        user.apple_user_id = social_id
    elif provider == "google":
        user.google_user_id = social_id
    elif provider == "linkedin":
        user.linkedin_user_id = social_id
    
    db.add(user)
    db.commit()
    db.refresh(user)
    
    return user


def link_social_account(
    db: Session,
    user: User,
    provider: str,
    social_id: str,
) -> User:
    """
    为已有用户绑定社交账号
    
    场景：用户用邮箱注册后，想添加 Apple/Google 登录方式
    """
    if provider == "apple":
        user.apple_user_id = social_id
    elif provider == "google":
        user.google_user_id = social_id
    elif provider == "linkedin":
        user.linkedin_user_id = social_id
    
    db.commit()
    db.refresh(user)
    
    return user


def unlink_social_account(
    db: Session,
    user: User,
    provider: str,
) -> bool:
    """
    解绑社交账号
    
    注意：如果用户没有密码且只有一个社交登录方式，不能解绑
    """
    # 检查是否可以解绑
    linked_providers = get_linked_providers(user)
    has_password = user.hashed_password and not user.hashed_password.startswith("social:")
    
    if len(linked_providers) <= 1 and not has_password:
        return False  # 不能解绑最后一个登录方式
    
    if provider == "apple":
        user.apple_user_id = None
    elif provider == "google":
        user.google_user_id = None
    elif provider == "linkedin":
        user.linkedin_user_id = None
    
    db.commit()
    return True


def get_linked_providers(user: User) -> list:
    """获取用户已绑定的社交账号列表"""
    providers = []
    if user.apple_user_id:
        providers.append("apple")
    if user.google_user_id:
        providers.append("google")
    if user.linkedin_user_id:
        providers.append("linkedin")
    return providers


def update_user_last_login(db: Session, user: User) -> User:
    """更新用户最后登录时间"""
    user.last_login_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(user)
    return user


# ==================== 辅助方法 ====================

def get_or_create_social_user(
    db: Session,
    provider: str,
    social_id: str,
    email: Optional[str],
    full_name: Optional[str] = None,
    email_verified: bool = True,
) -> tuple[User, bool]:
    """
    获取或创建社交登录用户
    
    Returns:
        (user, is_new_user)
    """
    # 1. 先通过社交 ID 查找
    user = get_user_by_social_id(db, provider, social_id)
    if user:
        update_user_last_login(db, user)
        return user, False
    
    # 2. 如果有邮箱，通过邮箱查找
    if email:
        from app.crud.user import crud_user
        user = crud_user.get_by_email(db, email)
        if user:
            # 用户存在但未绑定此社交账号，自动绑定
            link_social_account(db, user, provider, social_id)
            update_user_last_login(db, user)
            return user, False
    
    # 3. 创建新用户
    user = create_user_from_social(
        db=db,
        provider=provider,
        social_id=social_id,
        email=email,
        full_name=full_name,
        email_verified=email_verified,
    )
    
    return user, True