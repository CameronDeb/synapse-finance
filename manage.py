# manage.py
import argparse
import sys

# This setup allows the script to access the Flask app context,
# including the database and models, without running the web server.
from app import app, db
from app.models import User

def grant_pro_access(email):
    """Grants Pro access to a user by their email."""
    with app.app_context():
        user = db.session.scalar(db.select(User).where(User.email == email))
        if not user:
            print(f"Error: User with email '{email}' not found.")
            return

        if user.is_pro:
            print(f"Info: User '{email}' already has Pro access.")
            return
            
        user.subscription_tier = 'pro'
        # We don't set a stripe ID because this is a manual override
        db.session.commit()
        print(f"Success! User '{email}' has been granted Pro access.")

def revoke_pro_access(email):
    """Revokes Pro access from a user by their email."""
    with app.app_context():
        user = db.session.scalar(db.select(User).where(User.email == email))
        if not user:
            print(f"Error: User with email '{email}' not found.")
            return

        if not user.is_pro:
            print(f"Info: User '{email}' is already on the Free plan.")
            return
            
        user.subscription_tier = 'free'
        # Consider how to handle Stripe subscription if they have one.
        # For a simple beta, we assume they don't.
        user.stripe_subscription_id = None
        db.session.commit()
        print(f"Success! User '{email}' has been downgraded to the Free plan.")


if __name__ == '__main__':
    # Set up the command-line argument parser
    parser = argparse.ArgumentParser(description='Manage user access for Synapse Finance.')
    subparsers = parser.add_subparsers(dest='command', required=True)

    # Create the parser for the "grant-pro" command
    parser_grant = subparsers.add_parser('grant-pro', help='Grant Pro access to a user.')
    parser_grant.add_argument('email', type=str, help='The email address of the user to upgrade.')

    # Create the parser for the "revoke-pro" command
    parser_revoke = subparsers.add_parser('revoke-pro', help='Revoke Pro access from a user.')
    parser_revoke.add_argument('email', type=str, help='The email address of the user to downgrade.')

    # Parse the arguments from the command line
    args = parser.parse_args()

    # Execute the corresponding function
    if args.command == 'grant-pro':
        grant_pro_access(args.email)
    elif args.command == 'revoke-pro':
        revoke_pro_access(args.email)
