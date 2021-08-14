# CGM-M1-Pro-Parser
CGM M1 Pro has the option to search by certain criteria. The results of these searches can be exported to text files.
Unfortunately (like most things in the software), this functionality hasn't been updated for about 2 decades.
The lists don't share a common format, they don't even share the same line width.
This makes working with lists outside of CGM M1 Pro basically impossible (perhaps this by design).
This parser fills the gap and enables exporting to a sane format.

## A Word of Caution
If at all possible, please avoid using CGM M1 Pro. It is an abysmal product.

## Usage
For now, the best way to use the parser is via command line

```bash
./Parser.py input.txt output.csv
```

this creates a list of patient IDs found in the input file. Using the optional `-a` flag, it is possible to extract all 
meta information for each patient record. The actual text, while parsed, is not currently exported.

## Testing
Some simple test input can be found in the `test_input` folder. Unit tests are planned but not yet implemented.