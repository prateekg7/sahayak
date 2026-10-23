# 0011 — Household Membership and Multi-User Sharing Model

Status: Accepted
Date: 2026-10-23

## Context

Phase 9 (Home and Family Module) introduces multi-user shared resources (shared lists, chores, pantry items). Up to this point, all modules (Academics, Productivity, Finance, Health, Career) operated on strict single-user ownership where every query filters by `user_id == principal.user_id`.

Voice interactions over Alexa+ require simple, natural onboarding without complex access control configuration, while maintaining strict isolation: a user who is not a member of a household must never read or mutate that household's shared data.

## Options Considered

1. **Entity-level access control lists (ACLs):** Each list or chore maintains a list of permitted user IDs. While flexible, this creates high voice friction, complex authorization checks, and potential integrity drift.
2. **Household tenancy with roles (`owner`, `member`) and invite codes (Selected):** Users belong to one or more households. A household has an `owner` (the creator) and `members`. Members collaborate on all household resources. Access is granted via single-use 6-character invite codes expiring in 48 hours.
3. **Fine-grained RBAC:** Detailed permission sets (e.g. `list:write`, `chore:assign`, `household:admin`). Excessive cognitive overhead for family voice scenarios and unnecessary complexity for Alexa+ tool schemas.

## Decision

We adopt **Option 2: Household Tenancy with Roles and Expiring Invite Codes**.

### 1. Data Model
- `home.households`: Represents a family or living group (`id`, `name`, `created_by`, `created_at`).
- `home.memberships`: Links `core.users` to `home.households` with role `owner` or `member` (`id`, `household_id`, `user_id`, `role`, `joined_at`). Unique constraint on `(household_id, user_id)`.
- `home.invites`: Expiring single-use invite codes (`id`, `household_id`, `code`, `created_by`, `created_at`, `expires_at`, `used_at`, `used_by`). Codes are 6 uppercase alphanumeric characters (e.g., `H7K9M2`) with a unique index, valid for 48 hours.

### 2. Authorization & Verification (`assert_member`)
- Every service query or mutation touching household data takes the verified `user_id` and the target `household_id`.
- The generic helper `assert_member(household_id, user_id, required_role=None)` checks active membership.
- If the user is not a member, the helper raises `ForbiddenError` (or `NotFoundError` on lookup paths) to prevent tenant enumeration.
- If `required_role == 'owner'` is requested (e.g. generating invite codes or removing members), non-owners are rejected with `ForbiddenError`.

### 3. GDPR and Deletion Semantics
- When a user exercises GDPR right-to-be-forgotten / data deletion:
  1. The user's memberships and unused invite codes created by the user are deleted.
  2. If the user was the sole owner and other members exist, ownership automatically transfers to the earliest-joined member.
  3. If no other members remain in the household, the household and all associated shared records (lists, chores, pantry items) are deleted.

## Consequences

- Simple voice UX: Users can say "Join household with code ABC123" or "Create a household named Baker Street".
- Robust authorization: Centralized `assert_member` eliminates authorization omissions across all home module tools (`shared_list`, `chores`, `pantry_recipes`).
- Reversibility: Household tenancy tables are isolated in schema `home` and can be migrated or updated without impacting `core` or other modules.
