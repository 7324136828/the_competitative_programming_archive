export const CODE_TEMPLATES = {
  python: `# Solution in Python 3
import sys

def solve():
    # Read all input from standard input
    input_data = sys.stdin.read().split()
    if not input_data:
        return
    
    # Example for A + B:
    if len(input_data) >= 2:
        try:
            a = int(input_data[0])
            b = int(input_data[1])
            print(a + b)
        except ValueError:
            print("Invalid integer input")

if __name__ == '__main__':
    solve()
`,

  cpp: `// Solution in C++
#include <iostream>
#include <vector>
#include <string>
#include <algorithm>

using namespace std;

int main() {
    // Fast I/O
    ios_base::sync_with_stdio(false);
    cin.tie(NULL);

    long long a, b;
    if (cin >> a >> b) {
        cout << (a + b) << "\\n";
    }

    return 0;
}
`,

  java: `// Solution in Java
import java.util.Scanner;

public class Solution {
    public static void main(String[] args) {
        Scanner sc = new Scanner(System.in);
        if (sc.hasNextLong()) {
            long a = sc.nextLong();
            long b = sc.nextLong();
            System.out.println(a + b);
        }
        sc.close();
    }
}
`
};

export const DEFAULT_LANGUAGE = 'python';

