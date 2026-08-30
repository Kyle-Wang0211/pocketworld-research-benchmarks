// Build-only link probe. The linker force-loads every object from the VIO core
// archive, so this empty entry point validates the complete static dependency
// closure without adding any runtime or product behavior.
int main() { return 0; }
