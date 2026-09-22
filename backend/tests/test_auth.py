import pytest
from app.auth import _hash_password, authenticate, current_user, verify_password
from app.models import Membership, Organization, User

@pytest.mark.asyncio
async def test_password_hash_and_server_side_session(db):
    org = Organization(name="Auth Test")
    user = User(email="owner@example.test", password_hash=_hash_password("correct horse battery staple"), display_name="Owner")
    db.add_all([org, user])
    await db.flush()
    db.add(Membership(organization_id=org.id, user_id=user.id, role="owner"))
    await db.flush()
    assert verify_password("correct horse battery staple", user.password_hash)
    assert not verify_password("wrong password", user.password_hash)
    session, authenticated_user, membership, token, csrf = await authenticate(db, user.email, "correct horse battery staple", org.id)
    assert authenticated_user.id == user.id
    assert membership.role == "owner"
    assert len(token) >= 43
    assert len(csrf) >= 43
    current = await current_user(token, db)
    assert current.user_id == user.id
    assert current.organization_id == org.id
    session.revoked_at = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
    await db.flush()
    with pytest.raises(Exception):
        await current_user(token, db)
