import bcrypt

stored_hash_from_csharp = "$2a$12$IkMlwhEtups3JXggylcxe.k9xN5aMlYlby4qTPg8Re8obFZ/ltZCO"
password_to_check = "P@ssw0rd"

# Verify using python-bcrypt -> bcrypt.checkpw(input, stored_hash)
# input = input to check, stored_hash = hash from c# and stored in a database
is_valid = bcrypt.checkpw(
    password_to_check.encode('utf-8'),
    stored_hash_from_csharp.encode('utf-8')
)

print(f"Python Verification Result: {is_valid}") # Outputs: True