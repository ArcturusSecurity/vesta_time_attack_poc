# Vesta time attack PoC
Overengineered? I wouldn't know the MEANING of the term, dear boy...

# Development braindump
NB: A lot of the below hasn't been implemented. This code will be left in an unfinished
state.

We perform say 50000 requests for the first character, and assume it's the character 
which takes the longest time. We then update our current guessed code and begin work on
the second character. Repeat for all.

TODO?: During the above, we will keep the top three guesses for each position in the code as
a fallback in case our guess was wrong somehow. Regardless, this gives a massively
reduced number of attempts compared to brute forcing the full keyspace.

So to run the attack:
we fire off 5000 requests for A000000000
we store the results
we fire off 5000 requests for B000000000
we store the results
and so on, until we reach the limit of our character set.

Then, after we filter out the outliers from the time set, we sum the times for each 
character and assume the character with the lowest time is the correct one. We also 
store the character with the 2nd and 3rd lowest time. just in case.

Using that information, we continue to attack the second character:
we fire off 5000 requests for XA00000000, where X is our guessed character
we store the results
we fire off 5000 requests for XB00000000, where X is our guessed character
and so on.

Then we filter out the outliers again. We repeat this until we have attempted a guess on
all 10 charcters in the reset code. We should by this point have 3 potential guesses for 
each position in the 10-character long code. In other words, that's 3^10. 59049. Achievable. 

With that list of potentials, we then actually attempt to change the password on the vesta installation.

This program should be cancellable at any point and able to pick up from where it left
off. This is desirable due to the large amount of requests that need to be made. if we
^C during the running of the program, trap it and dump the current state to a 
human-readable json file. this file will contain everything needed to resume the program
at a later stage.

Future ideas / looking back:
Attempt each character simultaneously and give each a 'confidence vote' before moving on
to guess the next character. Round-robin through all possibilities with 10 requests at a
time. Exercise left for the reader.
