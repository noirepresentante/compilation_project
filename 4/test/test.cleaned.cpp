#include <iostream>
#include <vector>
#include <string>
#include <cmath>
int add(int x, int y) { return x + y; }
bool isPrime(int n) {
if (n <= 1) return false;
if (n == 2) return true;
if (n % 2 == 0) return false;
for (int i = 3; i * i <= n; i += 2) {
if (n % i == 0) return false;
}
return true;
}
double average(const std::vector<int>& v) {
if (v.empty()) return 0.0;
long long sum = 0;
for (int x : v) sum += x;
return static_cast<double>(sum) / v.size();
}
int factorial(int n) {
int result = 1;
int i = 2;
while (i <= n) {
result *= i;
++i;
}
return result;
}
int main() {
int a = 5; int b = 3;
int c = 0;
c = a + b * 2 - (a / 2);
bool ok = (c > 0) && (a != b) || !(b < 0);
if (ok) {
std::cout << "ok: c=" << c << "\n";
} else {
std::cout << "not ok\n";
}
std::vector<int> nums;
for (int i = 1; i <= 20; i++) {
if (isPrime(i)) nums.push_back(i);
}
int s = add(a, b);
std::cout << "add(a,b)=" << s << "\n";
std::cout << "avg(primes)=" << average(nums) << "\n";
std::cout << "factorial(6)=" << factorial(6) << "\n";
std::string tricky = "this is not a comment: // and neither is /* ... */";
char quote = '\'';
std::cout << tricky << " " << quote << "\n";
return 0;
}
